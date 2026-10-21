use std::env;

const DEFAULT_RABBIT_URL: &str = "amqp://user:password@localhost:5672/gunlinux_bot";
const DEFAULT_DONATE_URL: &str = "http://127.0.0.1:6016/donate";
const DEFAULT_QUEUE: &str = "bs_donats";
const DLQ_SUFFIX: &str = ".dlq";

#[derive(Debug, Clone)]
pub struct Config {
    /// Broker URI, including the virtual host in the path.
    pub rabbit_url: String,
    pub donate_url: String,
    pub queue: String,
    /// Routing key for failed messages on the `dlq` exchange; defaults to `<queue>.dlq`.
    pub dlq_routing_key: String,
}

impl Config {
    pub fn from_env() -> Self {
        let queue = env_or("BEER_STAT", DEFAULT_QUEUE);
        let dlq_routing_key = env_or("BEER_DLQ", &format!("{queue}{DLQ_SUFFIX}"));
        Self {
            rabbit_url: env_or("RABBIT_URL", DEFAULT_RABBIT_URL),
            donate_url: env_or("BEER_URL", DEFAULT_DONATE_URL),
            queue,
            dlq_routing_key,
        }
    }
}

fn env_or(key: &str, default: &str) -> String {
    env::var(key).unwrap_or_else(|_| default.to_string())
}
