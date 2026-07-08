# Role Verification & Audio Bridge Test Report

**Date:** 2026-06-13 13:40:27

## 1. Web Voice Calling & Local WebSocket Connections

| Role | Connection | Chunks Received | Errors |
|---|---|---|---|
| sellers | ✅ OK | 46 | None |
| buyers | ✅ OK | 37 | None |
| rfqs | ✅ OK | 68 | None |

## 2. Silence Detection (5-Second watchdog nudge)

| Role | Nudge Detected | Nudge Delay | Status |
|---|---|---|---|
| sellers | Yes | 5.66s | ✅ PASS |
| buyers | Yes | 6.16s | ✅ PASS |
| rfqs | Yes | 6.66s | ✅ PASS |

## 3. Jitter & Audio Resampling Latency Stats

| Role | Avg Interval | Min Interval | Max Interval | Jitter (StdDev) |
|---|---|---|---|---|
| sellers | 148.5ms | 0.1ms | 6159.4ms | 909.3ms |
| buyers | 185.5ms | 0.1ms | 6672.4ms | 1096.5ms |
| rfqs | 107.2ms | 0.0ms | 7176.5ms | 870.2ms |

## 4. Role pitch & RFQs Pitch Verification

### SELLERS (✅ PASS)
> Hi Surya, this is Devika from Procucev Bangalore. I am calling about our platform, GMT, Get My Quote. Thousands of verified buyers are posting requirements there, and our AI matches them to suppliers like you, so inquiries come directly to you. Registration is free and you get 2 RFQs free to start. And for your email, I have s-u-r-y-a at g-m-a-i-l dot c-o-m, is that correct? Also, I'll send all details on email, so you'll have the complete package, including about our CONNECT plan. Do you have any quick questions?

### BUYERS (✅ PASS)
> Hi, this is Adithi from Procucev Enterprise Solutions, Bangalore. We help companies like yours with cost-effective procurement solutions. Are you interested in hearing more? Regarding your email, I have s-u-r-y-a at g-m-a-i-l dot c-o-m – is that correct?

### RFQS (✅ PASS)
> Haan Surya, main Radhika bol rahi hoon, Procucev Bangalore se. Humne aapko ek invitation mail bheja hai, hamari platform GMT, yaani Get My Quote par ek requirement ke liye. Aap jab register karke login karenge, toh aap complete details aur RFQ download kar sakte hain. Aur aapka email address, s-u-r-y-a at g-m-a-i-l dot com hai na? Main isi par details bhej rahi hoon.

## 5. Gmail/Email Letter-by-letter Confirmation

### SELLERS (✅ PASS)
> Hi Surya, this is Devika from Procucev Bangalore. I am calling about our platform, GMT, Get My Quote. Thousands of verified buyers are posting requirements there, and our AI matches them to suppliers like you, so inquiries come directly to you. Registration is free and you get 2 RFQs free to start. And for your email, I have s-u-r-y-a at g-m-a-i-l dot c-o-m, is that correct? Also, I'll send all details on email, so you'll have the complete package, including about our CONNECT plan. Do you have any quick questions?

### BUYERS (✅ PASS)
> Hi, this is Adithi from Procucev Enterprise Solutions, Bangalore. We help companies like yours with cost-effective procurement solutions. Are you interested in hearing more? Regarding your email, I have s-u-r-y-a at g-m-a-i-l dot c-o-m – is that correct?

### RFQS (✅ PASS)
> Haan Surya, main Radhika bol rahi hoon, Procucev Bangalore se. Humne aapko ek invitation mail bheja hai, hamari platform GMT, yaani Get My Quote par ek requirement ke liye. Aap jab register karke login karenge, toh aap complete details aur RFQ download kar sakte hain. Aur aapka email address, s-u-r-y-a at g-m-a-i-l dot com hai na? Main isi par details bhej rahi hoon.

