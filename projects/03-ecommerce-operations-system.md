# E-commerce operations system (Mur Mur Objects)

**Context:** my own lighting brand. **Status:** live since July 2026.

## The problem

Orders arrive from three channels (Faire wholesale, Etsy and our own shop). Each lamp is 3D-printed in-house. To know real margins I need orders, costs, production, materials and stock in one place.

## What I built

One connected workbook that is the single source of truth for revenue, costs, production and stock. It deliberately uses formulas and scripts, not AI: the simplest technology that solves the problem well.

```mermaid
flowchart LR
    F[Faire] --> O[Orders<br/>stable internal IDs,<br/>source channel]
    E[Etsy] --> O
    W[Own shop] --> O
    O --> OI[Order items]
    OI --> P[Products and SKUs]
    O --> PL[Order P&L<br/>VAT, platform fees,<br/>shipping, commissions]
    P --> PQ[Production and<br/>print queue]
    PQ --> M[Materials, components,<br/>packaging]
    M --> INV[Inventory]
    PL --> D[Dashboard:<br/>contribution profit and margins]
    INV --> D
    D -.nightly.-> GH[(Snapshot to a private<br/>repository with full history)]
```

## Design choices

- **Stable internal order IDs** so the same order is never counted twice across syncs.
- **Reconciliation** of calculated totals against each platform's own totals.
- **Field documentation and sync logs** inside the workbook, so it can be handed over.
- **Nightly backup** to a repository, with full change history.

## Stack

Google Sheets · Google Apps Script · GitHub Actions
