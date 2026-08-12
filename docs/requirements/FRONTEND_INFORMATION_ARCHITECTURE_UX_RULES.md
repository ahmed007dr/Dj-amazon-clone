# FRONTEND INFORMATION ARCHITECTURE & UX RULES

> **Status:** Mandatory Global Frontend Rule  
> **Purpose:** Prevent oversized vertical pages and enforce a scalable, maintainable, professional Frontend architecture.

---

## 1. Core Rule — No Giant Vertical Pages

Never build a large feature as one extremely long page containing every section, form, table, setting, report, and action vertically.

An excessively long page is considered an **architectural smell**, not merely a visual issue.

When a page becomes large or contains multiple independent responsibilities:

**STOP → ANALYZE → SPLIT → DESIGN NAVIGATION → THEN CODE**

Do not solve the problem by simply adding more sections to the same page.

---

# 2. Information Architecture Comes Before Coding

Before implementing any large Frontend feature, analyze its information architecture.

Identify:

1. Main sections
2. Sub-sections
3. Related workflows
4. Independent responsibilities
5. Required routes
6. Main tabs
7. Nested tabs
8. Internal sidebar candidates
9. Detail pages
10. Drawers / modals
11. Reusable components
12. Potentially oversized pages

Do not start coding a complex feature before deciding how the information should be structured.

---

# 3. Main Tabs

When a feature contains several major functional areas, use **Main Tabs**.

Example:

```text
Orders
├── Overview
├── Orders
├── Returns
├── Analytics
└── Settings
```

The main page should not contain all five areas vertically.

Each major responsibility should have its own navigational context.

---

# 4. Nested Tabs

If one Main Tab contains several related sub-sections, use **Nested Tabs**.

Example:

```text
Orders
│
├── Overview
│
├── Orders
│   ├── All
│   ├── Pending
│   ├── Processing
│   └── Completed
│
├── Returns
│   ├── Requested
│   ├── Approved
│   └── Rejected
│
└── Settings
```

Do not overuse nested tabs.

If nesting becomes confusing or deep, prefer an **Internal Sidebar** or separate routes.

---

# 5. Internal Sidebar

Use an Internal Sidebar when a feature contains many sections that belong to the same functional domain.

Example:

```text
┌──────────────────┬──────────────────────────────────────────┐
│ Orders           │                                          │
│                  │          Current Section                 │
│ Overview         │                                          │
│ Orders           │          Content                         │
│ Returns          │                                          │
│ Customers        │                                          │
│ Analytics        │                                          │
│ Settings         │                                          │
└──────────────────┴──────────────────────────────────────────┘
```

This Sidebar is different from the application's **Global Sidebar**.

The Global Sidebar handles application-level navigation.

The Internal Sidebar handles navigation inside one major feature.

---

# 6. Route-Based Architecture

If a section is large enough to deserve independent navigation, give it its own route.

Example:

```text
/orders
/orders/overview
/orders/list
/orders/returns
/orders/analytics
/orders/settings
```

Use independent routes when they improve:

- Maintainability
- Code splitting
- Navigation
- Browser history
- Deep linking
- Permissions
- Testing
- Performance

Do not avoid routes merely to keep the route count small.

---

# 7. Dashboard Rule

Dashboards and Overview pages should summarize information.

They may contain:

- KPIs
- Important statistics
- Alerts
- Recent activity
- Quick actions
- Small charts
- Status summaries

They should NOT become containers for:

- Huge tables
- Large forms
- Full settings
- Complete reports
- Every possible action
- Every detailed record

The Overview should answer:

> "What is happening?"

Then navigation should answer:

> "Where do I go to manage or inspect it?"

---

# 8. Large Forms

Never create an unnecessarily long form containing dozens of fields with no structure.

For large forms, use:

- Sections
- Tabs
- Accordions
- Stepper / Wizard
- Separate routes where appropriate

Example:

```text
Product
│
├── Basic Information
├── Details
├── Pricing
├── Inventory
├── Permissions
└── Review
```

The user should not have to endlessly scroll through a single giant form.

---

# 9. Tables

Large data-management screens should follow a clear hierarchy.

Recommended structure:

```text
Page Header
    ↓
Summary / KPIs
    ↓
Tabs / Status Navigation
    ↓
Search + Filters + Actions
    ↓
Data Table
    ↓
Pagination
```

Do not stack multiple unrelated tables, statistics, forms, filters, and reports vertically without clear separation.

---

# 10. Detail Pages

If an item has significant details, do not force the user to scroll through a giant list page.

Use:

- Dedicated Detail Page
- Drawer
- Side Panel
- Modal
- Nested Route

Example:

```text
Orders
   ↓
Orders Table
   ↓
Click Order
   ↓
/orders/123
   ↓
Order Details
   ├── Overview
   ├── Customer
   ├── Items
   ├── Payment
   ├── Shipping
   ├── Timeline
   └── Activity
```

Choose the interaction based on the complexity and importance of the information.

---

# 11. Component Responsibility

Components must have clear responsibilities.

Avoid giant components such as:

```text
HugeOrderPage.jsx
HugeCustomerPage.jsx
HugeSettingsPage.jsx
```

Instead, decompose them:

```text
OrderPage
├── OrderHeader
├── OrderTabs
├── OrderOverview
├── OrderItems
├── OrderPayment
├── OrderShipping
├── OrderTimeline
└── OrderActivity
```

A component should not become a dumping ground for unrelated business logic and UI.

---

# 12. Reusable Layout System

Create reusable layout patterns that can be used across the entire application.

Examples:

```text
FeatureLayout
TabbedLayout
SidebarLayout
DetailLayout
ListLayout
SettingsLayout
FormLayout
DashboardLayout
```

Do not invent a completely different navigation pattern for every page.

The application should have a consistent UX language.

---

# 13. Page Size Warning Signs

Treat the following as warning signs:

- Excessive vertical scrolling
- Many unrelated sections
- Multiple large tables on one page
- Multiple large forms on one page
- Large settings sections mixed with operational data
- Analytics mixed with CRUD operations
- Detailed records rendered below summary content
- Repeated sections
- Extremely large React components
- Hundreds or thousands of lines in one page component
- Too many responsibilities handled by one route

When several of these appear, reconsider the architecture before continuing.

---

# 14. Decision Rule

Before creating or expanding a page, ask:

1. Does this page contain more than one major responsibility?
2. Is the page becoming excessively long?
3. Can the content be divided into logical groups?
4. Does the user need all sections visible at the same time?
5. Are some sections rarely used?
6. Are there many settings?
7. Should some details move to a Detail Page?
8. Would Tabs improve navigation?
9. Would an Internal Sidebar be clearer?
10. Should some sections become independent routes?

If multiple answers are **YES**, do not continue expanding the same page.

Redesign the Information Architecture first.

---

# 15. Anti-Pattern — Forbidden by Default

Avoid this architecture:

```text
Page
│
├── Header
├── Statistics
├── Filters
├── Table
├── Form
├── Another Table
├── Another Form
├── Settings
├── Analytics
├── History
├── Logs
├── Permissions
├── More Statistics
├── More Forms
└── More Tables
        ↓
   Endless Scroll
```

This is not considered a professional default architecture for a large application.

---

# 16. Preferred Patterns

## Pattern A — Main Tabs

```text
Feature
├── Overview
├── Management
├── Analytics
├── Activity
└── Settings
```

## Pattern B — Internal Sidebar

```text
Feature
└── Internal Sidebar
    ├── Overview
    ├── Management
    ├── Reports
    ├── Activity
    └── Settings
```

## Pattern C — Routes

```text
Feature
├── List
├── Create
├── Detail
├── Edit
└── Settings
```

## Pattern D — Main + Nested Tabs

```text
Feature
├── Overview
├── Management
│   ├── All
│   ├── Active
│   └── Archived
├── Reports
└── Settings
```

Choose the simplest structure that provides clear navigation.

---

# 17. Do Not Use Tabs Just to Hide Bad Architecture

Tabs are not a solution for dumping everything into one page.

Do not create:

```text
Tab 1 = 2000 lines
Tab 2 = 1500 lines
Tab 3 = 2500 lines
```

If a Tab itself becomes huge, it needs further decomposition.

Use:

- Nested Tabs
- Internal Sidebar
- Routes
- Detail Pages
- Dedicated workflows

when appropriate.

---

# 18. Responsive Behavior

The navigation architecture must work across:

- Desktop
- Tablet
- Mobile

Do not simply shrink a desktop layout.

For mobile:

- Tabs may become horizontally scrollable
- Internal Sidebars may collapse
- Navigation may become a dropdown or drawer
- Dense tables may become cards or horizontally scrollable containers
- Large forms may become step-based
- Actions may move into contextual menus

The information hierarchy must remain clear.

---

# 19. Performance Considerations

Good Information Architecture should also support performance.

Avoid rendering every section of a large feature simultaneously if the user does not need them simultaneously.

Prefer:

- Route-level code splitting
- Lazy loading
- Conditional rendering
- Pagination
- Server-side filtering where appropriate
- Independent data loading for independent sections

Do not fetch and render the entire feature simply because all sections exist somewhere in the application.

---

# 20. Permissions

Navigation structure should respect permissions.

If a user cannot access a section:

- Do not expose unnecessary navigation
- Do not load unnecessary data
- Do not render inaccessible controls

Tabs, Sidebars, Routes, and Actions should all respect the application's permission model.

---

# 21. Consistency Across the Application

Once a navigation pattern is established for a domain, reuse it.

For example:

```text
Orders
Customers
Inventory
Subscriptions
Finance
Staff
Reports
Settings
```

should not each invent completely different UX patterns without a strong reason.

The application should feel like **one product**, not a collection of unrelated pages.

---

# 22. AI / Claude Code Workflow

For every NEW large Frontend feature, Claude Code must follow this process:

```text
STEP 1
Inspect the existing Frontend architecture.

↓

STEP 2
Understand the existing routing, layouts, components, design system,
permissions, and navigation patterns.

↓

STEP 3
Analyze the requested feature.

↓

STEP 4
Identify major sections and responsibilities.

↓

STEP 5
Determine whether the feature requires:

- Main Tabs
- Nested Tabs
- Internal Sidebar
- Independent Routes
- Detail Pages
- Drawers
- Modals
- Wizards
- Reusable Components

↓

STEP 6
Propose the Information Architecture.

↓

STEP 7
Show the proposed route/component/navigation tree.

↓

STEP 8
Identify any existing components that should be reused.

↓

STEP 9
Identify any existing components that should be refactored.

↓

STEP 10
Wait for architecture approval before implementing
a large or structural change.
```

---

# 23. Mandatory Planning Output

Before implementing a large Frontend feature, provide a plan similar to:

```text
FEATURE: Orders

CURRENT PROBLEM:
The current page contains too many responsibilities and is vertically oversized.

PROPOSED STRUCTURE:

/orders
├── overview
├── orders
│   ├── all
│   ├── pending
│   ├── processing
│   └── completed
├── returns
├── analytics
└── settings

LAYOUT:
- FeatureLayout
- Internal navigation
- Main content area

REUSABLE COMPONENTS:
- PageHeader
- StatCard
- DataTable
- FilterBar
- StatusTabs
- EmptyState
- Pagination

DETAIL:
- /orders/:id

CREATE / EDIT:
- Dedicated workflow or Drawer depending on complexity

PERMISSIONS:
- Apply existing permission system

RESPONSIVE:
- Desktop Sidebar
- Mobile Drawer / compact navigation
```

The exact structure must be adapted to the feature rather than copied blindly.

---

# 24. Existing Codebase Comes First

Do not introduce a new architecture blindly.

Before creating a new layout or navigation component:

1. Inspect existing layouts.
2. Inspect existing routes.
3. Inspect existing reusable components.
4. Inspect existing design-system components.
5. Inspect existing patterns in similar features.
6. Reuse existing patterns where appropriate.
7. Refactor duplicated patterns when beneficial.

Do not create duplicate components that already exist.

---

# 25. Avoid Over-Engineering

The purpose of this rule is NOT to create unnecessary complexity.

Do not turn a simple page into:

```text
5 Routes
4 Tabs
3 Nested Tabs
2 Sidebars
8 Drawers
```

when the feature only needs one simple page.

Use the **simplest architecture that keeps the information hierarchy clear and the page maintainable**.

---

# 26. Final UX Principle

The goal is not:

> "How can we fit everything into one page?"

The goal is:

> "How can we help the user reach the information or operation they need with the least confusion and unnecessary scrolling?"

---

# 27. Final Mandatory Rule

## STOP → ANALYZE → SPLIT → NAVIGATE → CODE

Whenever a Frontend page starts becoming excessively long:

**DO NOT KEEP ADDING SECTIONS.**

Stop and determine whether the content should be divided into:

- Main Tabs
- Nested Tabs
- Internal Sidebar
- Routes
- Detail Pages
- Drawers
- Modals
- Wizards
- Reusable Components

The Frontend must prioritize:

1. Information hierarchy
2. User experience
3. Maintainability
4. Reusability
5. Performance
6. Consistency
7. Accessibility
8. Responsive behavior

over simply minimizing the number of pages or routes.

---

## Enforcement

This document is a **Global Frontend Architecture Rule**.

Claude Code must consult and follow it whenever:

- Creating a new Frontend feature
- Creating a new page
- Expanding an existing page
- Refactoring navigation
- Designing dashboards
- Designing CRUD interfaces
- Designing settings
- Designing reports
- Designing complex forms
- Designing complex data tables

If the requested implementation conflicts with these rules, Claude Code must explicitly point out the conflict and propose a better Information Architecture before proceeding.
