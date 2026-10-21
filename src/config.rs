use std::env;

const DEFAULT_RABBIT_URL: &str = "amqp://user:password@localhost:5672/gunlinux_bot";
const DEFAULT_DONATE_URL: &str = "http://127.0.0.1:6016/donate";
const DEFAULT_QUEUE: &str = "bs_donats";

#[derive(Debug, Clone)]
pub struct Config {
    /// Broker URI, including the virtual host in the path.
    pub rabbit_url: String,
    pub donate_url: String,
    pub queue: String,
}

impl Config {
    pub fn from_env() -> Self {
        Self {
            rabbit_url: env_or("RABBIT_URL", DEFAULT_RABBIT_URL),
            donate_url: env_or("BEER_URL", DEFAULT_DONATE_URL),
            queue: env_or("BEER_STAT", DEFAULT_QUEUE),
        }
    }
}

fn env_or(key: &str, default: &str) -> String {
    env::var(key).unwrap_or_else(|_| default.to_string())
}
