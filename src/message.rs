use chrono::{DateTime, SecondsFormat, Utc};
use serde::{Deserialize, Serialize};

/// Donor name used when DonationAlerts sends an empty one.
pub const ANONYMOUS_NAME: &str = "Anonym";

/// Raw DonationAlerts donation payload published onto `bs_donats`.
/// Unknown keys are ignored on purpose: the producer forwards the whole gateway
/// payload (ids, recipient, provider metadata) and this consumer needs a few
/// fields only.
#[derive(Debug, Clone, Deserialize)]
pub struct DonationPayload {
    /// Donor display name; empty or missing when the donor has none.
    #[serde(default)]
    pub name: Option<String>,
    /// Amount in the donor's currency; sent as an int or a float.
    #[serde(default)]
    pub amount_in_user_currency: Option<f64>,
    /// Optional donor message.
    #[serde(default)]
    pub message: Option<String>,
}

/// Body posted to the BeerStat `/donate` endpoint.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Donation {
    pub date: String,
    pub value: i64,
    pub name: String,
    pub commentary: Option<String>,
}

impl DonationPayload {
    /// Only paid donations are forwarded; everything else is acked and ignored.
    pub fn is_donation(&self) -> bool {
        self.amount_in_user_currency
            .is_some_and(|amount| amount > 0.0)
    }

    pub fn to_donation(&self, now: DateTime<Utc>) -> Donation {
        Donation {
            date: now.to_rfc3339_opts(SecondsFormat::Micros, false),
            value: self.amount_in_user_currency.map(round_amount).unwrap_or(0),
            name: self.donor_name(),
            commentary: self.commentary(),
        }
    }

    /// An empty donor name becomes [`ANONYMOUS_NAME`], because the API requires
    /// a non-empty name.
    fn donor_name(&self) -> String {
        match self.name.as_deref().map(str::trim) {
            Some(name) if !name.is_empty() => name.to_string(),
            _ => ANONYMOUS_NAME.to_string(),
        }
    }

    /// A missing or blank message is no commentary at all.
    fn commentary(&self) -> Option<String> {
        let message = self.message.as_deref()?.trim();
        (!message.is_empty()).then(|| message.to_string())
    }
}

/// Python's `round()` rounds halves to even; keep that so amounts stay identical.
fn round_amount(amount: f64) -> i64 {
    amount.round_ties_even() as i64
}

#[cfg(test)]
mod tests {
    use super::{ANONYMOUS_NAME, Donation, DonationPayload, round_amount};
    use chrono::{DateTime, Utc};

    fn at(ts: &str) -> DateTime<Utc> {
        ts.parse().expect("timestamp")
    }

    fn donation(payload: &DonationPayload) -> Donation {
        payload.to_donation(at("2026-10-20T19:27:31.123456Z"))
    }

    fn parse(json: &str) -> DonationPayload {
        serde_json::from_str(json).expect("parse")
    }

    #[test]
    fn converts_amount_in_user_currency_to_int() {
        let payload = parse(r#"{"name":"test_user","amount_in_user_currency":100.5}"#);
        assert_eq!(
            donation(&payload),
            Donation {
                date: "2026-10-20T19:27:31.123456+00:00".into(),
                value: 100,
                name: "test_user".into(),
                commentary: None,
            }
        );
    }

    #[test]
    fn accepts_integer_and_fractional_amounts() {
        assert_eq!(
            parse(r#"{"amount_in_user_currency":333}"#).amount_in_user_currency,
            Some(333.0)
        );
        assert_eq!(
            parse(r#"{"amount_in_user_currency":333.5}"#).amount_in_user_currency,
            Some(333.5)
        );
    }

    #[test]
    fn rounds_fractional_amounts_like_python() {
        assert_eq!(round_amount(100.6), 101);
        assert_eq!(round_amount(100.5), 100);
        assert_eq!(round_amount(101.5), 102);
    }

    #[test]
    fn skips_missing_and_zero_amounts() {
        assert!(!parse(r#"{"name":"test_user"}"#).is_donation());
        assert!(!parse(r#"{"amount_in_user_currency":0}"#).is_donation());
        assert!(!parse(r#"{"amount_in_user_currency":null}"#).is_donation());
        assert!(!parse(r#"{"amount_in_user_currency":-10}"#).is_donation());
        assert!(parse(r#"{"amount_in_user_currency":1}"#).is_donation());
    }

    #[test]
    fn empty_name_becomes_anonym() {
        for payload in [
            parse(r#"{"name":null,"amount_in_user_currency":10}"#),
            parse(r#"{"name":"","amount_in_user_currency":10}"#),
            parse(r#"{"name":"   ","amount_in_user_currency":10}"#),
            parse(r#"{"amount_in_user_currency":10}"#),
        ] {
            assert_eq!(donation(&payload).name, ANONYMOUS_NAME);
        }
    }

    #[test]
    fn keeps_non_empty_name() {
        let payload = parse(r#"{"name":" loki ","amount_in_user_currency":10}"#);
        assert_eq!(donation(&payload).name, "loki");
    }

    #[test]
    fn empty_message_is_no_commentary() {
        for payload in [
            parse(r#"{"message":null,"amount_in_user_currency":10}"#),
            parse(r#"{"message":"","amount_in_user_currency":10}"#),
            parse(r#"{"message":"  ","amount_in_user_currency":10}"#),
            parse(r#"{"amount_in_user_currency":10}"#),
        ] {
            assert_eq!(donation(&payload).commentary, None);
        }
    }

    #[test]
    fn passes_message_as_commentary() {
        let payload = parse(r#"{"message":" ahaha ","amount_in_user_currency":10}"#);
        assert_eq!(donation(&payload).commentary.as_deref(), Some("ahaha"));
    }

    #[test]
    fn parses_donation_alerts_payload_and_ignores_unknown_keys() {
        // Verbatim copy of payload.json, so the real gateway shape stays covered.
        let payload = parse(
            r#"{"amount":333,"amount_in_user_currency":333,"created_at":"2026-10-11 18:29:48","currency":"RUB","id":192333054,"is_shown":0,"message":"ahaha","message_type":"text","name":"Donations","payin_system":null,"reason":"default","recipient":{"avatar":"https://static-cdn.jtvnw.net/jtv_user_pictures/d06e4fd1-1d67-4034-9a85-792a6185e044-profile_image-300x300.png","code":"gunlinux","name":"gunlinux","user_id":5116810},"recipient_name":"gunlinux","shown_at":null,"username":"loki"}"#,
        );

        assert!(payload.is_donation());
        assert_eq!(
            donation(&payload),
            Donation {
                date: "2026-10-20T19:27:31.123456+00:00".into(),
                value: 333,
                name: "Donations".into(),
                commentary: Some("ahaha".into()),
            }
        );
    }

    #[test]
    fn serializes_the_api_body() {
        let payload = parse(r#"{"amount_in_user_currency":333,"message":""}"#);
        assert_eq!(
            serde_json::to_value(donation(&payload)).expect("serialize"),
            serde_json::json!({
                "date": "2026-10-20T19:27:31.123456+00:00",
                "value": 333,
                "name": ANONYMOUS_NAME,
                "commentary": null,
            })
        );
    }
}
