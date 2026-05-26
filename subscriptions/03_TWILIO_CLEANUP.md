# Twilio — Release Numbers or Close Account

**Current bleed: ~$3.30/mo ($39.60/yr)**
**Balance: $40.00**
**Usage: Zero SMS sent. 4 inbound calls (spam), last Oct 2025.**

## Phone Numbers to Release

| Number | Type | Monthly Cost | Last Activity |
|--------|------|-------------|---------------|
| +447723145724 | UK Mobile | ~$1.15/mo | Oct 2025 (spam call) |
| +18339784123 | US Toll-Free | ~$2.15/mo | Never used |

## Option A: Release Numbers, Keep Account (Recommended)

If you might use Twilio for SMS notifications or automation later:

### Steps
1. Log in to https://console.twilio.com
2. Go to Phone Numbers > Manage > Active Numbers
3. Click each number > Release this number
4. Confirm release
5. $40 balance stays in account for future use

### CLI Alternative
```bash
source ~/.oh-my-zsh/custom/keys.zsh
# List numbers
curl -s -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" \
  "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID/IncomingPhoneNumbers.json" | \
  python3 -c "import sys,json; [print(f'{n[\"sid\"]} {n[\"phone_number\"]}') for n in json.load(sys.stdin)['incoming_phone_numbers']]"

# Release a number (replace SID)
curl -X DELETE -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" \
  "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID/IncomingPhoneNumbers/PNXXXXXXXXXX.json"
```

## Option B: Close Account Entirely

If you're sure you won't need SMS/voice API:

1. Log in to https://console.twilio.com
2. Go to Settings > General
3. Click "Close Account"
4. $40 balance is forfeited

## Recommendation

Release both numbers now. Keep the account open with $40 balance — could be useful for automated court filing notifications, 2FA backup, or sending demand letters via SMS. Zero ongoing cost once numbers are released.
