# Problem Statement

## Background

Global pharmaceutical and temperature-sensitive supply chains move millions of shipments per year
across multi-modal routes spanning ocean freight, air cargo, road, and rail. Each leg involves
hand-offs between carriers, customs dwell times, and temporary storage in warehouses and yards —
all of which create windows where temperature control can silently fail and regulatory compliance
can be breached.

At the same time, natural disruptions (typhoons, port strikes, congestion events) routinely affect
dozens or hundreds of in-transit shipments simultaneously, forcing rapid rerouting decisions under
incomplete and conflicting information.

---

## The Problem

**A single control-tower operator is responsible for 100–300 active shipments at any given time.**
When a disruption event fires or a cold-chain sensor alarm triggers, that operator faces four
simultaneous questions with no unified tool to answer any of them:

1. **Which of my shipments are actually hit by this disruption — and how badly?**
   Today, the operator cross-references a disruption notification with a spreadsheet of active
   shipment routes, manually estimating overlap. For a typhoon affecting the South China Sea, this
   takes 30–60 minutes and still misses shipments in transit that are not yet updated in the TMS.

2. **What are my rerouting options, and will a detour maintain cold-chain continuity?**
   Rerouting proposals come from freight forwarders via email, with no structured comparison of
   cost, delay, and reefer capability across alternatives. The operator cannot easily see which
   option preserves the 2–8 °C window and which breaks it.

3. **Which fleet assets are idle right now and can be redeployed to cover the gap?**
   Fleet visibility sits in a separate system. Matching an idle reefer truck at Hamburg to an
   impacted cold-chain shipment in Rotterdam takes several phone calls and manual status checks.

4. **Has any cold-chain shipment already breached its temperature range — and is there still time
   to act?**
   Sensor alarms arrive as raw email alerts with no severity classification, no degree-minute
   accumulation, no MKT calculation, and no regulatory citation. The operator does not know whether
   a 1-hour excursion at 9 °C is a minor GDP event or a critical product-loss scenario.

---

## Who Is Affected

**Primary user: a control-tower operator** at a pharmaceutical logistics company or third-party
logistics provider (3PL) responsible for temperature-sensitive products (vaccines, biologics,
oncology drugs, diagnostics). The operator:

- Manages 100–300 concurrent shipments spanning global routes.
- Is accountable to GDP (Good Distribution Practice), WHO PQS, and FSMA regulations.
- Works a 12-hour shift and must triage incoming alerts while also managing the routine queue.
- Has access to 3–5 disconnected systems: TMS, WMS, fleet tracker, sensor platform, and email.

**Secondary impact: pharmaceutical quality and compliance teams** who depend on the operator's
excursion reports for batch disposition decisions. A late, incomplete, or incorrectly classified
excursion report can delay a GDP Article 35 disposition assessment by 24–48 hours, during which
the affected product remains in uncertain status.

---

## Why It Matters

| Impact | Quantification |
|---|---|
| Time to triage a single disruption event | 30–60 minutes manually vs. seconds with RouteX |
| Cold-chain excursions per year (industry) | ~15–25% of pharmaceutical shipments experience at least one temperature deviation (IQVIA / WHO data) |
| Average cost of a single spoilage event | $50,000–$500,000 USD depending on product value and batch size |
| Regulatory penalty risk (GDP Article 35 non-compliance) | Shipment quarantine, batch recall, or market withdrawal |
| Fleet idle capacity loss | 40+ assets × average 20h idle time = 800+ wasted capacity-hours per operational cycle |

The four questions the operator cannot currently answer quickly are each individually expensive.
Combined — during a concurrent disruption and cold-chain crisis — they represent a decision-making
gap that routinely results in delayed action, product loss, or regulatory non-compliance.

---

## Why Existing Solutions Fall Short

| Current approach | Why it fails |
|---|---|
| **TMS (Transport Management System)** | Shows shipment status but has no disruption impact scoring, no cold-chain excursion classification, and no reroute comparison tool. |
| **Fleet management system** | Tracks asset locations but has no link to active shipment exceptions, so idle asset redeployment requires manual matching. |
| **Sensor platform alarms** | Fires raw threshold breaches with no degree-minute accumulation, no MKT calculation, no regulatory tier classification, and no actionability signal (detected before vs. after delivery). |
| **Freight forwarder email / phone** | Ad hoc, unstructured, not comparable across options, and has no cold-chain continuity field. |
| **Spreadsheet triage** | Brittle, slow to update, produces no audit trail, and cannot cross-reference four data sources simultaneously in real time. |

None of these tools answers the control-tower operator's four questions from a unified interface
with a shared data model, deterministic scoring, and a full audit trail per decision. RouteX does.
