mod config;
mod message;

use std::env;
use std::time::Duration;

use anyhow::{Context, Result};
use chrono::Utc;
use futures_util::StreamExt;
use lapin::{
    Connection, ConnectionProperties, Consumer,
    options::{BasicAckOptions, BasicConsumeOptions, BasicRejectOptions, QueueDeclareOptions},
    types::{AMQPValue, FieldTable},
};
use tracing::{debug, error, info, warn};
use tracing_subscriber::EnvFilter;

use crate::message::QueueMessage;

const CONSUMER_TAG: &str = "beerstat";
const RECONNECT_DELAY: Duration = Duration::from_secs(5);
const HTTP_TIMEOUT: Duration = Duration::from_secs(10);

#[tokio::main]
async fn main() {
    dotenvy::dotenv().ok();
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();

    let config = config::Config::from_env();
    if env::var_os("RABBIT_VHOST").is_some() {
        warn!(
            "RABBIT_VHOST is ignored; put the virtual host in RABBIT_URL, e.g. amqp://host:5672/gunlinux_bot"
        );
    }
    info!(
        queue = %config.queue,
        donate_url = %config.donate_url,
        "starting beerstat consumer"
    );

    let http = reqwest::Client::builder()
        .timeout(HTTP_TIMEOUT)
        .build()
        .expect("build http client");

    loop {
        tokio::select! {
            _ = shutdown_signal() => {
                info!("shutting down");
                return;
            }
            result = consume(&config, &http) => match result {
                Ok(()) => warn!("amqp stream ended, reconnecting"),
                Err(err) => error!("consumer failed: {err:#}"),
            },
        }

        tokio::select! {
            _ = shutdown_signal() => {
                info!("shutting down");
                return;
            }
            _ = tokio::time::sleep(RECONNECT_DELAY) => {}
        }
    }
}

/// Ctrl-C or SIGTERM (the signal `docker stop` / systemd send).
async fn shutdown_signal() {
    let ctrl_c = async {
        let _ = tokio::signal::ctrl_c().await;
    };

    #[cfg(unix)]
    let terminate = async {
        match tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()) {
            Ok(mut signal) => {
                signal.recv().await;
            }
            Err(err) => {
                warn!(error = %err, "cannot listen for SIGTERM");
                std::future::pending::<()>().await;
            }
        }
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {}
        _ = terminate => {}
    }
}

async fn consume(config: &config::Config, http: &reqwest::Client) -> Result<()> {
    let connection = Connection::connect(&config.rabbit_url, ConnectionProperties::default())
        .await
        .context("connect to rabbitmq")?;
    let channel = connection.create_channel().await.context("open channel")?;

    let mut arguments = FieldTable::default();
    arguments.insert(
        "x-dead-letter-exchange".into(),
        AMQPValue::LongString("dlq".into()),
    );
    arguments.insert(
        "x-dead-letter-routing-key".into(),
        AMQPValue::LongString(format!("{}.dlq", config.queue).into()),
    );

    channel
        .queue_declare(
            &config.queue,
            QueueDeclareOptions {
                durable: true,
                auto_delete: false,
                ..Default::default()
            },
            FieldTable::default(),
        )
        .await
        .context("declare queue")?;

    info!(queue = %config.queue, "consuming");
    let mut consumer: Consumer = channel
        .basic_consume(
            &config.queue,
            CONSUMER_TAG,
            BasicConsumeOptions::default(),
            FieldTable::default(),
        )
        .await
        .context("start consuming")?;

    while let Some(delivery) = consumer.next().await {
        let delivery = delivery.context("receive delivery")?;

        if let Err(err) = handle(config, http, &delivery.data).await {
            error!(error = %err, "worker function failed");
            delivery
                .acker
                .reject(BasicRejectOptions { requeue: false })
                .await
                .context("reject message")?;
        } else {
            delivery
                .acker
                .ack(BasicAckOptions::default())
                .await
                .context("ack message")?;
        }
    }

    Ok(())
}

async fn handle(config: &config::Config, http: &reqwest::Client, payload: &[u8]) -> Result<()> {
    let message: QueueMessage = serde_json::from_slice(payload).context("parse queue message")?;
    debug!(
        event = %message.event,
        source = %message.source,
        data = ?message.data,
        "process event"
    );

    if !message.data.is_donation() {
        return Ok(());
    }

    let donation = message.data.to_donation(Utc::now());
    http.post(&config.donate_url)
        .json(&donation)
        .send()
        .await
        .context("post donation")?
        .error_for_status()
        .context("donate endpoint returned an error")?;

    Ok(())
}
