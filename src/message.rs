use chrono::{DateTime, SecondsFormat, Utc};
use serde::{Deserialize, Serialize};

/// Donation event published by the upstream bot onto the `bs_donats` queue.
/// Unknown keys are ignored on purpose: the producer adds fields (raw payloads,
/// provider metadata) that this consumer does not need.
#[derive(Debug, Clone, Deserialize)]
pub struct QueueEvent {
    pub event_type: String,
    pub user_name: Option<String>,
    pub amount: Option<f64>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct QueueMessage {
    pub event: String,
    pub data: QueueEvent,
    #[serde(default)]
    pub source: String,
}

/// Body posted to the BeerStat `/donate` endpoint.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Donation {
    pub date: String,
    pub value: i64,
    pub name: Option<String>,
}

impl QueueEvent {
    /// Only paid donations are forwarded; everything else is acked and ignored.
    pub fn is_donation(&self) -> bool {
        self.event_type == "DONATION" && self.amount.is_some_and(|amount| amount != 0.0)
    }

    pub fn to_donation(&self, now: DateTime<Utc>) -> Donation {
        Donation {
            date: now.to_rfc3339_opts(SecondsFormat::Micros, false),
            value: self.amount.map(round_amount).unwrap_or(0),
            name: self.user_name.clone(),
        }
    }
}

/// Python's `round()` rounds halves to even; keep that so amounts stay identical.
fn round_amount(amount: f64) -> i64 {
    amount.round_ties_even() as i64
}

#[cfg(test)]
mod tests {
    use super::{Donation, QueueEvent, QueueMessage, round_amount};
    use chrono::{DateTime, Utc};

    fn at(ts: &str) -> DateTime<Utc> {
        ts.parse().expect("timestamp")
    }

    fn donation(event: &QueueEvent) -> Donation {
        event.to_donation(at("2026-10-20T19:27:31.123456Z"))
    }

    #[test]
    fn converts_amount_to_int() {
        let event = QueueEvent {
            event_type: "DONATION".into(),
            user_name: Some("test_user".into()),
            amount: Some(100.5),
        };
        assert_eq!(
            donation(&event),
            Donation {
                date: "2026-10-20T19:27:31.123456+00:00".into(),
                value: 100,
                name: Some("test_user".into()),
            }
        );
    }

    #[test]
    fn rounds_fractional_amounts_like_python() {
        assert_eq!(round_amount(100.6), 101);
        assert_eq!(round_amount(100.5), 100);
        assert_eq!(round_amount(101.5), 102);
    }

    #[test]
    fn skips_non_donations_and_zero_amounts() {
        let mut event = QueueEvent {
            event_type: "SUBSCRIBE".into(),
            user_name: None,
            amount: Some(100.0),
        };
        assert!(!event.is_donation());

        event.event_type = "DONATION".into();
        assert!(event.is_donation());

        event.amount = Some(0.0);
        assert!(!event.is_donation());

        event.amount = None;
        assert!(!event.is_donation());
    }

    #[test]
    fn parses_minimal_queue_message() {
        let message: QueueMessage =
            serde_json::from_str(r#"{"event":"test_event","data":{"event_type":"DONATION"}}"#)
                .expect("parse");

        assert_eq!(message.source, "");
        assert_eq!(message.data.amount, None);
        assert_eq!(message.data.user_name, None);
        assert_eq!(message.event, "test_event");
    }

    #[test]
    fn parses_full_event_and_ignores_unknown_keys() {
        let message: QueueMessage = serde_json::from_str(
            r#"{
                "event": "test_event",
                "source": "test_source",
                "data": {
                    "event_type": "DONATION",
                    "billing_system": "stripe",
                    "user_name": "test_user",
                    "amount": 50.0,
                    "currency": "USD",
                    "message": "thanks!",
                    "raw_payload": {"nested": "data"},
                    "event": null
                }
            }"#,
        )
        .expect("parse");

        assert_eq!(message.source, "test_source");
        assert_eq!(message.data.amount, Some(50.0));
        assert!(message.data.is_donation());
    }
}
