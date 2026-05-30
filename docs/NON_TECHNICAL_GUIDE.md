# Store Intelligence — Complete Non-Technical Guide

### For Store Managers, Business Users, and Decision Makers

> **Who is this guide for?**
> This guide is written for people who run stores, make business decisions, or want to understand what this application does — without needing to know anything about computers, software, or programming.
>
> If you have never heard of Python, Docker, or APIs, that is perfectly fine. This document will explain everything using everyday language, real examples, and simple diagrams.

---

## Table of Contents

1. [The Problem This Application Solves](#1-the-problem)
2. [Why Would a Retail Store Want This?](#2-why-retail-stores-need-this)
3. [How the System Works — Plain English](#3-how-it-works)
4. [The Customer's Journey — From Door to Dashboard](#4-customer-journey)
5. [Key Concepts Explained Simply](#5-key-concepts)
6. [Understanding the Dashboard](#6-dashboard)
7. [Using Insights to Improve Sales](#7-using-insights)
8. [What Each Report Tells You — In Business Language](#8-reports)
9. [Complete Flow Diagram](#9-flow-diagram)
10. [Day in the Life of a Store Manager](#10-day-in-life)
11. [User Manual — How to Use the Application](#11-user-manual)
12. [How to Use This Application Without Any Technical Knowledge](#12-no-tech-needed)
13. [Glossary — All Important Terms](#13-glossary)
14. [Frequently Asked Questions](#14-faq)
15. [Troubleshooting Guide](#15-troubleshooting)

---

## 1. The Problem This Application Solves

### Think About Your Online Store

When a customer visits your website, you can see **everything**:

- How many people visited today
- Which products they looked at
- How long they spent on each page
- Which page made them leave
- How many added something to their cart vs. actually paid

This level of detail helps online stores improve constantly. They know exactly what is working and what is not.

### Now Think About Your Physical Store

When a customer walks into your physical store:

- You do not know how many people came in today (unless someone counts manually)
- You do not know which sections they visited
- You do not know how long they spent looking at products
- You do not know why they left without buying
- You do not know if your checkout queue is making people give up

**Your physical store is a complete blind spot.**

You are making decisions — which products to stock, where to place them, how many staff to schedule — based on guesswork and gut feel.

### What This Application Does

**Store Intelligence turns your physical store into an online store, analytically speaking.**

It reads your existing CCTV camera footage and automatically answers:

| Question | How the Application Answers It |
|----------|-------------------------------|
| How many customers came in today? | Counts every person who enters the door |
| Where do customers spend the most time? | Shows a colour-coded map of your store |
| Why are people not buying? | Shows where they drop off in their journey |
| Is my checkout queue too long? | Alerts you the moment a queue builds up |
| Is today's sales rate unusually low? | Automatically compares to your past 7 days |

---

## 2. Why Would a Retail Store Want This?

### The Numbers Tell the Story

Imagine 100 people walk into your store today.

- 80 walk around and browse
- 40 pick up a product and consider buying
- 20 walk to the checkout area
- 12 actually pay

That means **88 people left without buying**. Where did you lose them? Was it the product display? The long queue? A section nobody found interesting? Without data, you are guessing.

### Real Business Benefits

**Increase Sales Without More Customers**

If you can understand why 88 people left, you can fix it. Even moving 5 more people to complete a purchase means a 41% increase in sales — with the same number of customers walking in.

**Right Staff, Right Time**

If the application tells you that 80% of your customers arrive between 4 PM and 7 PM, you can schedule more staff during those hours and fewer during quiet periods. This saves money and improves customer service at the same time.

**Product Placement That Actually Works**

If the heatmap shows customers spend a lot of time in the fragrance section but almost never walk to the skincare section at the back, you can move skincare closer to fragrance. Sales go up. No guesswork required.

**Catch Problems Before They Cost You**

If your checkout queue has been growing for the last 20 minutes, the application sends an alert. You can open another billing counter before customers get frustrated and leave.

---

## 3. How the System Works — Plain English

Think of this system like having a very smart invisible observer standing in your store all day, every day, taking detailed notes about every customer.

Here is how it works in three simple steps:

### Step 1 — The Cameras Watch

Your existing CCTV cameras record video footage as they always have. Nothing changes about the cameras themselves.

```
CCTV Camera 1 (near the door)   →   Records who enters and exits
CCTV Camera 2 (main floor)      →   Records which sections people visit
CCTV Camera 3 (billing area)    →   Records checkout behaviour
```

**Important:** The system never records faces or identifies people. Every person's face is automatically blurred. The system only tracks movement patterns — not identity.

### Step 2 — The Computer Reads the Video

A computer programme watches the recorded video and automatically detects:

- Every time a person enters the store
- Every time a person exits
- Which section of the store a person is standing in
- How long they stayed in that section
- How many people are waiting at the checkout
- Whether a person is a staff member or a customer (staff wear uniforms)

Think of it like having a very attentive assistant who watches all the camera footage and writes down every observation in a neat notebook.

### Step 3 — The Dashboard Shows the Results

All those observations are instantly converted into easy-to-read reports and charts that appear on a dashboard — like the dashboard of a car, but for your store.

You open the dashboard in any web browser (like opening Google or Facebook) and you immediately see:

- How many customers are in the store right now
- How today's sales conversion rate compares to yesterday
- Which zones are busy and which are empty
- Whether there is a queue building at the checkout
- Any unusual situations that need your attention

---

## 4. The Customer's Journey — From Door to Dashboard

Let us follow a real customer — let us call her Priya — through the entire process.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    PRIYA'S JOURNEY THROUGH YOUR STORE                   │
└─────────────────────────────────────────────────────────────────────────┘

  2:15 PM                                                                  
  Priya walks                                                              
  through the door    ────────►  Camera 1 sees her enter                  
                                 System notes: "New visitor VIS_abc123     
                                 entered at 2:15 PM"                       
        │                                                                  
        ▼                                                                  
  2:16 PM                                                                  
  Priya walks to      ────────►  Camera 2 sees her in the Skincare zone   
  the Skincare                   System notes: "Visitor VIS_abc123         
  section                        entered Skincare zone at 2:16 PM"         
        │                                                                  
        ▼                                                                  
  2:18 PM                                                                  
  Priya picks up a    ────────►  System notes: "Visitor VIS_abc123 has    
  moisturiser and                been in Skincare for 2 minutes"           
  keeps looking                                                            
        │                                                                  
        ▼                                                                  
  2:22 PM                                                                  
  Priya walks to      ────────►  Camera 3 sees her join the queue         
  the checkout                   System notes: "Visitor VIS_abc123 entered
  (3 people waiting)             billing queue. Queue depth: 3 people"     
        │                                                                  
        ▼                                                                  
  2:25 PM                                                                  
  Priya pays for      ────────►  The billing machine records:             
  her moisturiser                "Transaction TXN_00441 at 2:25 PM        
  (₹899)                         value ₹899"                              
        │                                                                  
        ▼                                                                  
  The system matches Priya's checkout visit (2:22 PM) with the            
  transaction (2:25 PM) → marks her as a CONVERTED CUSTOMER               
        │                                                                  
        ▼                                                                  
  2:26 PM                                                                  
  Priya exits         ────────►  Camera 1 sees her leave                  
  the store                      Session complete: 11 minutes total        
        │                                                                  
        ▼                                                                  
  2:28 PM                                                                  
  Dashboard updates:             
  ┌──────────────────────────────────────────────────────────────────┐     
  │  Today's Visitors: 47   Conversion Rate: 21.3%   Queue: 2 deep  │     
  └──────────────────────────────────────────────────────────────────┘     
```

This entire process — from Priya walking in to her data appearing on your dashboard — happens **automatically**, in real time, with no human involvement.

---

## 5. Key Concepts Explained Simply

### 5.1 CCTV Clips

**What it means:** The video recordings from your security cameras.

**Simple explanation:** These are the same recordings your store already makes for security purposes. The application reads these recordings to understand customer behaviour. Think of the CCTV footage as the raw material — like unprocessed sugar cane. The application turns that raw material into refined, useful data — like sugar.

**Important:** The faces in the footage are automatically blurred before processing. No one's identity is ever recorded.

---

### 5.2 Events

**What it means:** Every significant thing that happens gets logged as an "event."

**Simple explanation:** Think of events like entries in a very detailed store diary. Every time something noteworthy happens, the system writes it down with the exact time.

Examples of events the system records:

| Event | What It Means | Real Example |
|-------|--------------|--------------|
| ENTRY | A customer walked in | "At 2:15 PM, Customer #47 entered through the main door" |
| EXIT | A customer walked out | "At 2:26 PM, Customer #47 left the store" |
| ZONE_ENTER | A customer entered a product area | "Customer #47 walked into the Skincare section" |
| ZONE_DWELL | A customer stayed somewhere for 30+ seconds | "Customer #47 has been in Skincare for 2 minutes" |
| ZONE_EXIT | A customer left a product area | "Customer #47 left the Skincare section after 6 minutes" |
| BILLING_QUEUE_JOIN | A customer joined the checkout queue | "Customer #47 joined the queue. 3 people waiting" |
| BILLING_QUEUE_ABANDON | A customer left the queue without buying | "Customer #12 left the queue after 8 minutes without purchasing" |
| REENTRY | A customer came back after leaving | "Customer who left at 1:30 PM re-entered at 1:45 PM" |

---

### 5.3 Visitor Sessions

**What it means:** The complete record of one customer's visit from the moment they enter until they leave.

**Simple explanation:** A visitor session is like a story of one customer's complete shopping trip. It has a beginning (when they walked in), a middle (everything they did inside), and an end (when they left and whether they bought something).

**Example:**

```
PRIYA'S SESSION — 29 May 2026
─────────────────────────────────────────
Arrived:        2:15 PM
Left:           2:26 PM
Total time:     11 minutes

Places visited: Skincare section (6 min)
                Billing area (4 min)

Did she buy?    YES — ₹899

Staff member?   NO (she is a customer)
─────────────────────────────────────────
```

The system creates one session record for every customer visit. These sessions are the foundation for calculating all your business metrics.

---

### 5.4 Conversion Rate

**What it means:** The percentage of visitors who actually purchased something.

**Simple explanation:** If 100 people walk into your store and 20 of them buy something, your conversion rate is 20%. This is the single most important metric for a retail store.

**The analogy:** Imagine you throw a party and invite 100 friends. 20 of them actually show up. Your "party conversion rate" is 20%. In retail, you want this number to be as high as possible.

```
CONVERSION RATE CALCULATION

100 customers walked in today
  └── 20 customers made a purchase

Conversion Rate = 20 ÷ 100 = 20%

Industry average for beauty retail: 15-25%
Your store today: 20% → RIGHT IN RANGE ✓

If you improve this to 25%:
100 customers × 25% = 25 purchases
That is 5 extra sales per 100 visitors — every single day
```

**Why it matters:** This single number tells you whether your store is effectively turning browsing into buying. If it drops suddenly, something is wrong — maybe a popular product is out of stock, or staff are not engaging customers, or the queue is too long.

---

### 5.5 The Conversion Funnel

**What it means:** A visual representation of how customers move through the buying journey — and where they drop off.

**Simple explanation:** Imagine a funnel — wide at the top, narrow at the bottom. At the top, all your customers pour in. At each stage, some of them "leak out" and don't continue. What's left at the bottom are the customers who actually purchased.

```
THE STORE FUNNEL

            100 customers entered
         ████████████████████████████
            ↓ 20% left without looking around
            
            80 customers browsed product zones
         ████████████████████████
            ↓ 50% left without going to checkout
            
            40 customers reached the billing area
         ████████████
            ↓ 50% abandoned the queue
            
            20 customers completed a purchase
         ██████
         
         CONVERSION RATE = 20%
```

**How to use it:** Each "leak" in the funnel is an opportunity. If 60 people are going to product zones but only 40 are going to billing, why are 20 people choosing not to buy after looking at products? Maybe your prices are not clearly displayed. Maybe staff are not helping them. This funnel tells you exactly where to focus your attention.

---

### 5.6 Heatmap

**What it means:** A colour-coded map of your store showing which areas are the busiest and which are quiet.

**Simple explanation:** Think of a weather temperature map — the kind you see on TV where red areas are hot and blue areas are cold. The store heatmap works the same way:

- **Hot (dark colour, high score)** = Many customers spent a lot of time here
- **Cool (light colour, low score)** = Few customers visited or they moved through quickly

```
EXAMPLE STORE HEATMAP

┌─────────────────────────────────────────┐
│                                         │
│  SKINCARE    ████████  Score: 100       │
│  (Very busy — 35 visits today)          │
│                                         │
│  HAIRCARE    ██████    Score: 68        │
│  (Moderately busy — 24 visits)          │
│                                         │
│  FRAGRANCE   ████      Score: 34        │
│  (Quiet — 12 visits today)              │
│                                         │
│  MAKEUP      ██        Score: 18        │
│  (Very quiet — 6 visits today)          │
│                                         │
└─────────────────────────────────────────┘

→ Action: Move Makeup section closer to
  the entrance, or put a promotional
  display to attract customers
```

**How to use it:** If a section consistently shows low scores, something is wrong. Either the products are not interesting, the section is hard to find, or the displays are not attractive. The heatmap helps you identify these problem areas quickly.

---

### 5.7 Queue Analytics

**What it means:** Information about how many customers are waiting at the checkout and for how long.

**Simple explanation:** Have you ever been at the back of a long queue at a supermarket and decided to just put your items back and leave? That is called queue abandonment. It is one of the biggest hidden causes of lost sales in retail.

Queue analytics tells you:

- **Queue depth right now** — How many people are waiting at the billing counter
- **Queue join rate** — How often customers join the queue throughout the day
- **Abandonment rate** — What percentage of people join the queue but leave before paying

```
QUEUE ANALYTICS EXAMPLE

2:00 PM - 3:00 PM today:

  Customers who joined checkout queue:  24
  Customers who completed payment:      18
  Customers who LEFT the queue:          6  ← abandoned!

  Abandonment Rate = 6 ÷ 24 = 25%

  This means 1 in 4 customers who decided to buy
  something changed their mind because of the wait.

  ALERT: When queue depth reaches 5+ people,
  open another billing counter immediately.
```

---

### 5.8 Anomalies (Automatic Alerts)

**What it means:** The system automatically detects when something unusual is happening and sends you an alert.

**Simple explanation:** Anomalies are like a smart smoke alarm for your store's performance. A smoke alarm does not require you to constantly check if there is a fire — it simply alerts you when something is wrong. Anomalies work the same way.

The system monitors three things automatically:

**Alert 1 — Queue Spike**
```
Situation: Your average queue depth at this time of day is 2 people.
           Suddenly, 8 people are waiting.
Alert:     ⚠ QUEUE_SPIKE — "Open an additional billing counter immediately"
```

**Alert 2 — Conversion Rate Drop**
```
Situation: Your store's average conversion rate is 22%.
           Today's rate has dropped to 12%.
Alert:     ⚠ CONVERSION_DROP — "Review floor staff positioning 
            and product engagement"
```

**Alert 3 — Dead Zone**
```
Situation: Your Makeup section normally gets visited every 10 minutes.
           Nobody has walked into that section in the last 30 minutes.
Alert:     ℹ DEAD_ZONE — "Check camera feed for Makeup section;
            verify display setup"
           (This might mean the display fell over or the 
            lights went out in that section)
```

---

## 6. Understanding the Dashboard

The dashboard is the "face" of the application — the screen you look at to understand how your store is doing. You access it by opening a web browser and going to the store's address (like opening a website).

### The Dashboard Sections

```
┌──────────────────────────────────────────────────────────────┐
│  🏪 Store Intelligence  [STORE_BLR_002 ▼]        ● LIVE     │
│  Bangalore Store 002           Last updated: 2:28 PM         │
├──────────────┬───────────────┬──────────────┬───────────────┤
│  VISITORS    │  CONVERSION   │    QUEUE     │  ABANDONMENT  │
│    TODAY     │     RATE      │    DEPTH     │     RATE      │
│              │               │              │               │
│     47       │    21.3%      │      3       │    12.5%      │
│              │               │              │               │
│ People who   │ 1 in 5 people │ People       │ 1 in 8 queue  │
│ entered the  │ are buying    │ waiting at   │ joiners left  │
│ store today  │               │ checkout     │ without buying│
├──────────────┴───────────────┼──────────────┴───────────────┤
│                              │                              │
│  VISITOR COUNT OVER TIME     │  CONVERSION FUNNEL           │
│                              │                              │
│  ↑ 50                        │  Entry      47 ████████████  │
│    40                        │  Browse     38 ██████████    │
│    30    ___                 │  Billing    21 █████         │
│    20  _/   \_               │  Purchase   10 ██            │
│    10 /       \__            │                              │
│     0─────────────           │  Drop-off at Billing: 50%!   │
│     10am  12pm  2pm          │                              │
├──────────────────────────────┼──────────────────────────────┤
│                              │                              │
│  ZONE HEATMAP                │  ACTIVE ALERTS               │
│                              │                              │
│  SKINCARE   ████████  100    │  ✓ No alerts right now       │
│  HAIRCARE   ██████     68    │                              │
│  FRAGRANCE  ████       34    │                              │
│  MAKEUP     ██         18    │                              │
│                              │                              │
└──────────────────────────────┴──────────────────────────────┘
```

### What Each Number Means

**Visitors Today (47)**
This is the total number of unique individual customers who entered your store today. Staff members are automatically excluded from this count. If this number is lower than usual, it might indicate a problem with footfall (fewer people walking past your store) rather than a conversion problem.

**Conversion Rate (21.3%)**
Out of every 100 customers who entered, 21 made a purchase. A healthy beauty retail store typically aims for 15-30%. If this drops suddenly, check the Alerts section.

**Queue Depth (3)**
There are currently 3 people waiting at the checkout counter. If this number climbs above 5, the system will alert you — this is the point where customers commonly start abandoning their purchase.

**Abandonment Rate (12.5%)**
Of all the customers who joined the checkout queue, 1 in 8 left before completing their purchase. This is a concerning metric — high abandonment often means the queue wait time is too long.

### The Visitor Chart

The line chart shows how customer traffic has moved through the day. Common patterns:

- **Morning rise, lunchtime peak, afternoon lull, evening peak** — typical retail pattern
- **Sudden drop mid-afternoon** — might indicate the store was too quiet, or a local event drew people elsewhere
- **Unusually high morning traffic** — might indicate a sale or promotion is working

### Reading the Funnel

The funnel shows where customers "drop off" in their journey:

```
If the biggest drop is between "Entry" and "Browse":
→ Customers are walking in but leaving immediately
→ Check: Is the entrance layout inviting? Are products visible?

If the biggest drop is between "Browse" and "Billing":
→ Customers are looking at products but not buying
→ Check: Are prices clearly displayed? Is staff helping customers?

If the biggest drop is between "Billing" and "Purchase":
→ Customers want to buy but giving up at the queue
→ Check: Is the queue too long? Are billing counters understaffed?
```

---

## 7. Using Insights to Improve Sales

### The Golden Rule

**Data without action is just numbers. Action without data is just guessing.**

Here is how to turn the dashboard information into real business improvements:

### Scenario 1: Low Conversion Rate

```
Dashboard shows: Conversion Rate dropped from 22% to 14%

Step 1: Check the Funnel
  → Where is the biggest drop happening?

Step 2a: If drop is at "Billing" stage
  → Open more billing counters
  → Train staff to assist faster
  
Step 2b: If drop is at "Browse" stage
  → Staff may not be engaging customers
  → Check product availability (out of stock?)
  → Review pricing visibility
  
Step 3: Monitor the dashboard for improvement
  → Did conversion rate recover after your action?
```

### Scenario 2: The Makeup Section is Empty

```
Dashboard shows: Makeup zone score = 12 (out of 100)
                 Skincare zone score = 100

Possible causes:
  1. Makeup section is physically far from the entrance
  2. Makeup products are not prominently displayed
  3. Makeup section is not well lit
  4. Customers do not know the section exists

Actions:
  1. Move makeup display closer to the entrance
  2. Create a promotional display at the store entrance
     pointing to the makeup section
  3. Ask your store designer to improve lighting and displays
  4. Train staff to mention makeup products to customers
     in the skincare section

Result to watch: Makeup zone score should gradually increase
```

### Scenario 3: Queue Building in the Afternoon

```
Dashboard shows: Queue depth at 2-4 PM is consistently 6+

Analysis:
  → This is a recurring daily pattern
  → Not a one-time anomaly

Action:
  → Schedule an additional staff member at billing
    specifically for the 2-4 PM window
  → Consider opening the second billing counter
    automatically at 2 PM every day

Cost savings: Avoiding 25% abandonment during peak hours
  If 20 customers are in queue during this period
  and 5 abandon (25%), each with potential ₹500 basket
  = ₹2,500 lost per day = ₹75,000 per month
```

---

## 8. What Each Report Tells You — Business Language

Here is what each section of the application reports, explained in plain business terms:

### Report 1: "Today's Store Performance" (Metrics)

**Business question it answers:** "How is my store doing right now, today?"

**What it shows:**
- Total customers who visited
- How many made a purchase (and what percentage that is)
- Average time spent in each product section
- Current checkout queue length
- Queue abandonment rate

**When to check it:** First thing in the morning (to see yesterday's summary), and periodically throughout the day to catch problems early.

---

### Report 2: "Customer Shopping Journey" (Funnel)

**Business question it answers:** "Where in the shopping process am I losing customers?"

**What it shows:** A step-by-step breakdown of how many customers completed each stage of the shopping journey, and how many dropped off at each stage.

**When to check it:** Weekly, to track improvement over time. If conversion rate drops suddenly, check the funnel immediately.

---

### Report 3: "Store Traffic Map" (Heatmap)

**Business question it answers:** "Which parts of my store are customers spending time in, and which are they ignoring?"

**What it shows:** A visual score for each product zone showing how many customers visited and how long they stayed.

**When to check it:** Weekly, or when considering a store layout change. Before and after making display changes to measure impact.

---

### Report 4: "Automatic Problem Alerts" (Anomalies)

**Business question it answers:** "Is anything going wrong right now that needs my immediate attention?"

**What it shows:** Automatic alerts when something unusual is detected — a sudden queue spike, a sharp drop in sales, or a product zone that no one is visiting.

**When to check it:** The dashboard alerts you automatically. You do not need to check this proactively — but if you see an alert, act on it immediately.

---

### Report 5: "System Health Check" (Health Status)

**Business question it answers:** "Is the application working correctly? Are all my cameras connected?"

**What it shows:**
- Whether the system is running normally
- Whether data is being received from each store's cameras
- A warning if data from a particular store has not arrived in the last 10 minutes (which might indicate a camera disconnection)

**When to check it:** If you think something is not working, or if the other reports are not updating.

---

## 9. Complete Flow Diagram

```
╔═══════════════════════════════════════════════════════════════════════╗
║                    HOW THE SYSTEM WORKS                               ║
╠═══════════════════════════════════════════════════════════════════════╣
║                                                                       ║
║  YOUR STORE'S CAMERAS                                                 ║
║  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               ║
║  │ Entry Camera │  │ Floor Camera │  │Billing Camera│               ║
║  │ (Door area)  │  │(Product zones│  │(Checkout area│               ║
║  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘               ║
║         └─────────────────┴─────────────────┘                        ║
║                           │                                           ║
║                    Video Recording                                    ║
║                           │                                           ║
║                           ▼                                           ║
║  ┌────────────────────────────────────────────────────────────────┐   ║
║  │              DETECTION ENGINE (The Smart Observer)             │   ║
║  │                                                                │   ║
║  │  • Counts people entering and exiting                         │   ║
║  │  • Identifies which zone each person is standing in           │   ║
║  │  • Tracks how long each person stays in each zone             │   ║
║  │  • Identifies staff vs. customers (by uniform)                │   ║
║  │  • Detects re-entry (same person coming back)                 │   ║
║  │  • Blurs all faces (privacy protection)                       │   ║
║  └──────────────────────────────┬─────────────────────────────────┘   ║
║                                 │                                     ║
║                    Structured observations                            ║
║                    (500 at a time)                                    ║
║                                 │                                     ║
║                                 ▼                                     ║
║  ┌────────────────────────────────────────────────────────────────┐   ║
║  │              INTELLIGENCE ENGINE (The Brain)                   │   ║
║  │                                                                │   ║
║  │  • Stores every observation in a secure database               │   ║
║  │  • Links observations to POS (billing) transaction data        │   ║
║  │  • Calculates conversion rates in real time                    │   ║
║  │  • Builds the shopping funnel                                  │   ║
║  │  • Creates the zone heatmap                                    │   ║
║  │  • Monitors for anomalies 24/7                                 │   ║
║  └──────────────────────────────┬─────────────────────────────────┘   ║
║                                 │                                     ║
║                    Live metrics every 2 seconds                       ║
║                                 │                                     ║
║                                 ▼                                     ║
║  ┌────────────────────────────────────────────────────────────────┐   ║
║  │              DASHBOARD (What You See)                          │   ║
║  │                                                                │   ║
║  │  Open in any browser on any device (phone, tablet, laptop)    │   ║
║  │                                                                │   ║
║  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌──────────────────┐    │   ║
║  │  │Visitors│  │Conv.   │  │Queue   │  │   Alerts &       │    │   ║
║  │  │ Today  │  │Rate    │  │Depth   │  │   Anomalies      │    │   ║
║  │  └────────┘  └────────┘  └────────┘  └──────────────────┘    │   ║
║  │                                                                │   ║
║  │  ┌────────────────────┐  ┌────────────────────────────────┐   │   ║
║  │  │   Visitor Chart    │  │   Conversion Funnel            │   │   ║
║  │  └────────────────────┘  └────────────────────────────────┘   │   ║
║  │                                                                │   ║
║  │  ┌────────────────────┐  ┌────────────────────────────────┐   │   ║
║  │  │   Zone Heatmap     │  │   Active Anomalies             │   │   ║
║  │  └────────────────────┘  └────────────────────────────────┘   │   ║
║  └────────────────────────────────────────────────────────────────┘   ║
╚═══════════════════════════════════════════════════════════════════════╝
```

---

## 10. Day in the Life of a Store Manager

Let us follow Rahul, the manager of an Apex Retail store in Bangalore, through a typical working day using the Store Intelligence dashboard.

### 9:00 AM — Morning Check

**What Rahul does:** Opens the dashboard on his tablet before the store opens.

**What he sees:**
```
Yesterday's Summary:
  Total visitors:    143
  Conversion rate:   19.2%  ← below his 22% target
  Busiest zone:      Skincare (score 100)
  Quietest zone:     Makeup (score 11)
  Queue abandonments: 18 (12.6%)
```

**What Rahul thinks:** Yesterday's conversion rate was below target. The makeup section had almost no visitors. He checks the funnel and sees the big drop is at the "Browse to Billing" stage.

**Rahul's action:** He speaks to his team during the morning briefing, asks staff to actively guide customers toward the makeup section and to help customers in the product zones by answering questions proactively.

---

### 11:30 AM — Mid-Morning Check

**What Rahul sees:**
```
Today so far (11:30 AM):
  Visitors:          32
  Conversion rate:   26.4%  ← above target!
  Queue depth:       1      ← comfortable
  Makeup zone score: 28     ← improving!
```

**What Rahul thinks:** The morning briefing worked. Staff engagement is up, conversion is above target, and more people are visiting the makeup section.

**Rahul's action:** Sends a quick message to his team — "Great start! Keep the energy up."

---

### 2:15 PM — Alert Notification

**What appears on Rahul's phone:**
```
⚠ ALERT — QUEUE_SPIKE
Current queue depth: 7 people
Your usual average at this time: 2 people
Suggested action: Open an additional billing counter
```

**What Rahul does:** Immediately calls a staff member from the floor to open the second billing counter.

**Result:** Within 5 minutes, the queue reduces to 3 people. The system stops showing the alert.

---

### 4:00 PM — Afternoon Review

**What Rahul checks:**
```
Today's heatmap (2 PM - 4 PM):
  Skincare:   ████████████  Score 100  (35 visitors)
  Haircare:   ██████████    Score 71   (25 visitors)
  Fragrance:  ████          Score 28   (10 visitors)
  Makeup:     ███           Score 22   ( 8 visitors)
```

**Insight:** Rahul notices that customers who visit Skincare (35 people) rarely walk over to Fragrance (10 people), even though fragrance products are popular. The two sections are at opposite ends of the store.

**Rahul's decision:** Plans to request the store layout team to move the top-selling fragrance products to a display near the Skincare section. He notes this in his weekly report with the heatmap data as evidence.

---

### 6:00 PM — Evening Summary

**What the dashboard shows:**
```
Today's Full Day:
  Total visitors:    198
  Conversion rate:   23.7%  ✓ Above 22% target!
  Revenue sessions:  47 purchases
  Best performing:   Skincare + Haircare
  Alert count:       1 (queue spike at 2:15 PM — resolved in 7 min)
  Staff exclusions:  4 staff members correctly excluded
```

**Rahul exports this summary** (by taking a screenshot of the dashboard) to include in his weekly report to headquarters.

---

### The Difference This Makes

| Without Store Intelligence | With Store Intelligence |
|---------------------------|------------------------|
| "I think we had a good day" | "198 customers, 23.7% conversion — data confirmed" |
| "The makeup section seems slow" | "Makeup score 22 — 4× lower than Skincare" |
| "The queue seemed long this afternoon" | "Queue hit 7 at 2:15 PM. We resolved it in 7 minutes" |
| "Yesterday felt below average" | "Conversion was 19.2% vs. 22% target — here's why" |

---

## 11. User Manual — How to Use the Application

### How to Start the Application

> **Important note for non-technical users:** You do not need to start the application yourself. Your IT team or system administrator will set it up and keep it running. Your job is simply to use the dashboard. Skip to "How to Access the Dashboard" below.

If you are the person responsible for starting the system:

1. Open the **Terminal** application on your computer (this is a text-based program)
2. Navigate to the application folder
3. Type: `docker compose up` and press Enter
4. Wait approximately 60 seconds until you see the message: `Application startup complete`
5. The application is now running

### How to Access the Dashboard

**This is all you need to do as a store manager:**

1. Open any web browser (Chrome, Safari, Firefox — any will work)
2. In the address bar at the top, type: `http://localhost:8000/dashboard`
3. Press Enter
4. The dashboard loads automatically

**From a phone or tablet on the same network:**
- Type the same address but replace `localhost` with your store computer's name or IP address (your IT team will give you this)

### Verifying the Application is Running

The top-right corner of the dashboard shows a coloured dot:

```
● LIVE     → Green pulsing dot = System is running and receiving data
● OFFLINE  → Grey dot = Dashboard is open but not receiving data
● ERROR    → Red dot = Something is wrong
```

If you see OFFLINE or ERROR, check with your IT team.

### What Each Screen Means

**Top Row — The Four Big Numbers**

| Number | Means | Good sign | Warning sign |
|--------|-------|-----------|--------------|
| Visitors Today | Total customers who entered | Matches your expected footfall | Much lower than usual |
| Conversion Rate | % who purchased | 20%+ for beauty retail | Below 15% |
| Queue Depth | People at checkout now | 3 or fewer | 6 or more |
| Abandonment Rate | % who gave up in queue | Below 15% | Above 25% |

**Middle Row — The Chart and Funnel**

The **Visitor Chart** (left side): Shows how traffic has moved through the day. Use this to spot your busiest periods and plan staffing.

The **Conversion Funnel** (right side): Shows where customers are dropping off. The biggest gap between any two bars is your biggest opportunity.

**Bottom Row — The Heatmap and Alerts**

The **Zone Heatmap**: Shows which sections are busy (bright, large squares) and which are quiet (dim, small squares). Sections with very low scores need attention — either a layout change or a promotional push.

The **Active Anomalies**: If there are no alerts, it shows a green "No anomalies detected" message. If alerts appear, read them and act immediately. Each alert includes a suggested action.

### Common Daily Tasks

**Task 1: Morning performance check**
1. Open dashboard
2. Note yesterday's conversion rate
3. Check which zones had the highest and lowest scores
4. Brief your team accordingly

**Task 2: Responding to a queue alert**
1. Alert appears: "Queue Spike — 6 people waiting"
2. Open second billing counter immediately
3. Watch queue depth number on dashboard — it should drop
4. Alert disappears once queue returns to normal

**Task 3: Weekly trend review**
1. Check this week's conversion rate vs. last week
2. Look at the funnel — has the biggest drop-off point changed?
3. Compare zone heatmaps — is any zone consistently underperforming?
4. Plan layout or staffing changes based on findings

---

## 12. How to Use This Application Without Any Technical Knowledge

### You Are Not Expected to Touch the Technical Parts

This application has two parts:
1. **The Engine** (invisible, runs in the background) — your IT team handles this
2. **The Dashboard** (what you see) — this is for you

You will never need to:
- Write any code
- Use the command line (the black text screen)
- Configure any databases
- Understand how cameras connect to computers

**Your only job is to open the dashboard in a browser and read the numbers.**

### Think of It Like a Car

You do not need to understand how a car engine works to drive. You just:
1. Turn the key (IT team starts the system)
2. Look at the dashboard (conversion rate, visitors, etc.)
3. Press the pedals (take action based on what you see)
4. Call a mechanic if something breaks (call IT support)

The Store Intelligence application is exactly the same.

### What You Will Actually Do, Step by Step

```
EVERY MORNING:
  1. Open your phone or tablet
  2. Open Chrome or Safari
  3. Go to: [your store's dashboard address]
  4. Look at the 4 big numbers
  5. Check if any alerts are showing (bottom right)
  6. Brief your team on what the data shows

DURING THE DAY:
  1. Glance at your phone when you get a notification
  2. If the queue number goes red — open another counter
  3. If a zone alert appears — check that section physically

EVERY EVENING:
  1. Take a screenshot of the dashboard
  2. Note what was high, what was low, what alerts happened
  3. Include this in your daily/weekly report
```

---

## 13. Glossary — All Important Terms

| Term | What It Means (Simple) |
|------|------------------------|
| **API** | The "backstage" part of the application that answers questions — like the kitchen of a restaurant that you don't see but that prepares your food. You never interact with this directly. |
| **Anomaly** | An automatic alert that something unusual is happening in your store. |
| **Billing Queue** | The line of customers waiting to pay at the checkout counter. |
| **Conversion Rate** | The percentage of visitors who made a purchase. 20% means 20 out of every 100 visitors bought something. |
| **CCTV Clips** | The video recordings from your security cameras that the system reads. |
| **Dashboard** | The web page that shows all your store's analytics in real time. You open this in a browser. |
| **Dead Zone** | An alert that means a particular section of your store has had no visitors for 30+ minutes. |
| **Dwell Time** | How long a customer spent in a particular section of the store. |
| **Event** | A single observation recorded by the system. For example: "Customer #47 entered the store at 2:15 PM." |
| **Footfall** | The total number of people who enter your store. |
| **Funnel** | A step-by-step view of the customer journey showing how many people completed each stage of shopping. |
| **Heatmap** | A colour-coded map showing which parts of your store are busiest. |
| **Queue Abandonment** | When a customer joins the checkout queue but leaves before paying. |
| **Queue Spike** | An alert that means the checkout queue has become much longer than usual. |
| **Re-entry** | When the same customer leaves the store and comes back again. The system counts them as one unique visitor, not two. |
| **Session** | The complete record of one customer's visit from entry to exit. |
| **Staff Exclusion** | The system's ability to automatically identify store staff by their uniforms and exclude them from customer counts. |
| **Visitor** | A customer who enters your store. Staff members are automatically excluded from this count. |
| **Zone** | A named section of your store (for example: Skincare, Haircare, Billing). |

---

## 14. Frequently Asked Questions

**Q: Does the system record or store customers' faces?**
A: No. All faces are automatically blurred before the system processes the video. The system only tracks movement and position — never identity. It cannot tell you who a specific person is.

---

**Q: How accurate is the visitor count?**
A: The system is designed to count individuals accurately, including when multiple people enter at the same time (a group). It is typically within 5% of the true count, which is far more accurate than manual counting.

---

**Q: What happens if a camera goes offline?**
A: The dashboard will show a "STALE_FEED" warning for that store, indicating that data has not been received in the last 10 minutes. Your IT team will be alerted.

---

**Q: Can I see data from multiple stores?**
A: Yes. The dashboard has a store selector dropdown at the top. Click on it to switch between your stores. Each store has its own set of analytics.

---

**Q: Does the system work in real time?**
A: Yes. The dashboard updates every 2 seconds. If a customer walks in right now, their visit will appear in the visitor count within seconds.

---

**Q: What about staff — are they counted as visitors?**
A: No. The system automatically detects staff members by their uniforms and excludes them from all customer metrics. This ensures your conversion rate and visitor counts are accurate.

---

**Q: Can I use the dashboard on my mobile phone?**
A: Yes. The dashboard works on any device with a web browser — phone, tablet, laptop, or desktop computer.

---

**Q: What does "Low Data Confidence" mean on the heatmap?**
A: This warning appears when there have been fewer than 20 customer sessions for the day. It means the heatmap scores may not yet be statistically reliable — you should check back later in the day when there is more data.

---

**Q: How far back can I see data?**
A: The default view shows "today's" data. For historical trends, you will need to ask your IT team to generate a report from the database.

---

**Q: What should I do if the dashboard shows "OFFLINE"?**
A: First, refresh your browser (press F5 or the refresh button). If it still shows OFFLINE, contact your IT team. This typically means the application server needs to be restarted.

---

**Q: How is the conversion rate calculated?**
A: The system links customer visits in the billing zone with actual transactions from your POS (billing machine). If a customer was at the billing area within 5 minutes before a transaction, they are counted as converted.

---

## 15. Troubleshooting Guide

| Problem | What It Looks Like | What to Do |
|---------|-------------------|------------|
| Dashboard won't load | Browser shows an error page | Contact IT team. Check that the application is running. |
| Status dot is grey (OFFLINE) | ● OFFLINE in top right | Refresh the browser. If still offline, contact IT team. |
| All numbers show dashes (—) | Visitors: — Conversion: — | The system just started. Wait 2-3 minutes for data to appear. |
| Numbers haven't changed in hours | Same numbers since morning | Check camera connections. Contact IT team. |
| "STALE_FEED" message for a store | Yellow warning on health check | A camera may be disconnected. Check camera physically. |
| Conversion rate shows 0.0% | 0% even though sales happened | POS (billing) data may not be connected. Contact IT team. |
| Queue alert not going away | Alert keeps repeating | Open another billing counter. The alert will clear when queue drops. |
| Heatmap shows no zones | Empty heatmap | Zone events have not been recorded yet. Check if cameras covering the floor area are working. |
| Dashboard very slow | Pages take long to load | Normal for first load. If it persists, contact IT team. |

---

*This document was prepared for the Purplle Tech Challenge 2026.*
*For technical setup and configuration, refer to README.md and docs/ARCHITECTURE.md.*
*For business decisions and data interpretation, this document is your complete reference.*
