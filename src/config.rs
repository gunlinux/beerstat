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
    /// Routing key for failed messages on the `dlq` exchange; defaults to
    /// `<queue>.dlq`. `None` means the queue is declared without dead-letter
    /// arguments, which a queue shared with a producer that never declared them
    /// requires (a mismatching re-declare fails with `PRECONDITION_FAILED`).
    pub dlq_routing_key: Option<String>,
}

impl Config {
    pub fn from_env() -> Self {
        let queue = env_or("BEER_STAT", DEFAULT_QUEUE);
        let dlq_routing_key = dlq_routing_key(env::var("BEER_DLQ").ok(), &queue);
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

/// `<queue>.dlq` when unset; an explicit empty value or `-`/`off`/`none`
/// disables dead-lettering, anything else is used verbatim as the routing key.
fn dlq_routing_key(value: Option<String>, queue: &str) -> Option<String> {
    let value = match value {
        Some(value) => value.trim().to_string(),
        None => return Some(format!("{queue}{DLQ_SUFFIX}")),
    };
    if value.is_empty()
        || value == "-"
        || value.eq_ignore_ascii_case("off")
        || value.eq_ignore_ascii_case("none")
    {
        return None;
    }
    Some(value)
}

#[cfg(test)]
mod tests {
    use super::dlq_routing_key;

    #[test]
    fn dlq_defaults_to_queue_suffix() {
        assert_eq!(
            dlq_routing_key(None, "donations").as_deref(),
            Some("donations.dlq")
        );
    }

    #[test]
    fn explicit_dlq_is_trimmed() {
        assert_eq!(
            dlq_routing_key(Some(" custom.dlq ".into()), "donations").as_deref(),
            Some("custom.dlq")
        );
    }

    #[test]
    fn empty_or_off_disables_dlq() {
        for value in ["", "  ", "-", "off", "NONE"] {
            assert_eq!(dlq_routing_key(Some(value.into()), "donations"), None);
        }
    }
}
