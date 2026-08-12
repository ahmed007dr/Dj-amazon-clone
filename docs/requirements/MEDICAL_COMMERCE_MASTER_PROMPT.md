# MEDICAL COMMERCE PLATFORM
## MASTER DISCOVERY, AUDIT, ARCHITECTURE & IMPLEMENTATION PLANNING PROMPT

You are acting as the **Lead Software Architect, Senior Backend Engineer, Senior Frontend Engineer, API Architect, E-commerce Architect, B2B Commerce Architect, Security Engineer, Database Architect, Localization Architect, Product Architect, and Technical Project Manager** for a new Medical Commerce Platform.

Your responsibility in this phase is **NOT to start coding**.

Your first responsibility is to deeply inspect the existing project, especially the existing frontend inside:

```text
full-temp/
```

Understand what already exists, determine what can be reused, identify what should be refactored, identify what is missing, and create a complete implementation strategy.

We explicitly prefer **incremental evolution and reuse** over rebuilding the project from zero.

---

# 1. PROJECT VISION

We want to build a professional and scalable:

# MEDICAL COMMERCE PLATFORM

The platform will initially target university students, especially:

- Medicine
- Pharmacy
- Science

The platform will sell:

- Medical supplies
- Medical accessories
- Medical equipment
- Student medical supplies
- Laboratory equipment
- Medical clothing
- Books and educational materials
- General medical products
- Pharmaceutical products
- Professional-only products
- Other products related to medical education and healthcare

The platform will later expand to support:

- Students
- Doctors
- Pharmacists
- Pharmacies
- Medical stores
- Warehouses
- Traders
- Suppliers
- Pharmaceutical companies
- Internal employees / sales representatives

The long-term goal is to transform the initial university-focused store into a large:

# B2C + B2B + Employee Sales + Marketplace Medical Commerce Platform

---

# 2. EXISTING PROJECT MUST BE REUSED

There is already an existing frontend/project.

The existing frontend is located at:

```text
full-temp/
```

You MUST inspect this folder deeply before proposing any frontend rewrite.

Do NOT assume that the project needs to be rebuilt from zero.

Determine:

### REUSE

Can be used exactly or almost exactly as it is.

### REUSE + REFACTOR

Good foundation but needs modifications.

### REBUILD

Architecture or implementation is unsuitable.

### REMOVE

Not relevant anymore.

### NEW

Does not exist and must be created.

Every proposed rewrite must have a technical justification.

Do NOT rewrite working components simply because you prefer a different style or library.

---

# 3. FIRST PHASE: COMPLETE PROJECT DISCOVERY

Before changing anything, inspect the entire repository.

You must understand:

- Root project structure
- Backend structure
- Frontend structure
- `full-temp/`
- Existing API architecture
- Authentication
- Authorization
- Routing
- State management
- Components
- Layouts
- Design system
- Styling
- Forms
- Tables
- Modals
- Notifications
- API clients
- Services
- Hooks
- Utilities
- Shared components
- Existing dashboards
- Existing user management
- Existing product functionality
- Existing inventory functionality
- Existing order functionality
- Existing payment functionality
- Existing file upload functionality
- Existing localization
- Existing responsive/mobile behavior
- Existing tests
- Existing deployment configuration
- Existing environment configuration

Do not rely only on filenames.

Read the actual implementation.

Search the codebase for existing business logic before proposing new modules.

---

# 4. FRONTEND AUDIT

Perform a complete audit of the frontend inside:

```text
full-temp/
```

Determine exactly what is being used.

Inspect:

- `package.json`
- Source structure
- Routes
- Pages
- Components
- Hooks
- State management
- API layer
- Authentication
- Layouts
- CSS/Tailwind/Bootstrap
- UI libraries
- Forms
- Tables
- Modals
- Charts
- Notifications
- File upload components
- i18n/localization
- RTL support
- Responsive behavior
- Error handling
- Loading states
- Empty states
- Existing dashboards

Determine whether the frontend is:

- React
- Vite
- Next.js
- Redux
- Redux Toolkit
- Zustand
- Context API
- React Query
- Tailwind
- Bootstrap
- Material UI
- Radix
- Other libraries

Do not assume. Verify by reading the project.

---

# 5. FRONTEND REUSABILITY MATRIX

Create a detailed table referencing actual files and directories.

Example:

| Existing Feature | Actual Path | Status | Reuse Strategy | Required Changes |
|---|---|---|---|---|
| Authentication | `...` | REUSE + REFACTOR | Extend | Add account types |
| Dashboard Layout | `...` | REUSE | Shared | Add portal routing |
| Product Card | `...` | REUSE + REFACTOR | Extend | Add access-aware states |
| Table | `...` | REUSE | Shared | Add commerce filters |
| ... | ... | ... | ... | ... |

Do this for all important existing modules.

Do not provide generic examples instead of actual paths.

---

# 6. EXISTING DESIGN SYSTEM

Analyze the existing design system.

Identify:

- Colors
- Typography
- Spacing
- Buttons
- Inputs
- Selects
- Modals
- Tables
- Cards
- Alerts
- Toasts
- Badges
- Navigation
- Sidebar
- Header
- Mobile navigation
- Responsive breakpoints
- RTL support
- Dark/light mode
- Icons
- Component conventions
- Form conventions
- Error handling conventions

Determine whether it can support the new Medical Commerce Platform.

If it is usable:

**REUSE IT.**

If changes are required:

Recommend a controlled evolution.

Avoid unnecessary UI rewrites.

---

# 7. EXISTING BACKEND / API AUDIT

Inspect the backend deeply.

Determine:

- Backend framework
- Applications/modules
- Models
- Serializers
- Views/ViewSets
- URLs
- Services
- Permissions
- Authentication
- Database
- Migrations
- Signals
- Background jobs
- Notifications
- File handling
- Payment integrations
- Existing business logic
- Existing tests
- Existing reports
- Existing employee/staff functionality if present

Identify reusable functionality for:

- Users
- Authentication
- Profiles
- Products
- Categories
- Inventory
- Orders
- Payments
- Notifications
- Files
- Audit logs
- Reporting
- Employees
- Customers

Do not duplicate existing business logic.

---

# 8. CURRENT ARCHITECTURE ASSESSMENT

Evaluate the existing system for:

- Maintainability
- Scalability
- Security
- API quality
- Database quality
- Frontend architecture
- Component reusability
- State management
- Performance
- Testing
- Deployment
- Extensibility
- Localization
- Employee/business workflows

For every area, assign:

```text
Excellent
Good
Acceptable
Needs Refactoring
Critical
```

Explain why.

---

# 9. REQUIRED PORTALS

The platform must contain at least four major portals/experiences:

## 1. ADMIN PORTAL

Complete system administration.

## 2. CUSTOMER PORTAL

Account area for customers.

## 3. ONLINE STORE

The actual shopping experience.

## 4. EMPLOYEE PORTAL

A dedicated portal for internal employees / sales representatives.

These portals must share the same backend and business rules while exposing different capabilities according to permissions.

---

# 10. ADMIN PORTAL

The Admin Portal must control the entire platform.

Admin should be able to manage:

### Users

- Students
- Doctors
- Pharmacists
- Pharmacies
- Warehouses
- Traders
- Suppliers
- Employees
- Other customer types

### Products

- Products
- Categories
- Subcategories
- Brands
- Manufacturers
- Product types
- Product visibility
- Product access policies
- Pricing
- Discounts
- Stock
- Batches
- Expiry
- Product images
- Product documents

### Orders

- Orders
- Order status
- Returns
- Refunds
- Payments
- Shipping

### Business

- Employees
- Employees' targets
- Sales performance
- Commissions
- Employee percentages
- Customer assignments
- Returns
- Profit
- Monthly performance

### Loyalty

- Points
- Tiers
- Rewards
- Discounts

### Marketing

- Coupons
- Promotions
- Referral system
- Campus ambassadors

### Operations

- Notifications
- Reports
- Audit logs
- System settings

Admin must have granular permission controls.

---

# 11. CUSTOMER PORTAL

The Customer Portal must adapt to the customer type.

Common capabilities:

- Profile
- Orders
- Cart
- Wishlist
- Addresses
- Notifications
- Points
- Discounts
- Coupons
- Invoices
- Reorder
- Account verification
- Documents where applicable

Additional capabilities should appear based on account type.

---

# 12. ONLINE STORE

The store must support:

- Product browsing
- Search
- Filtering
- Sorting
- Product details
- Cart
- Checkout
- Wishlist
- Reviews
- Order tracking
- Product recommendations
- Back-in-stock notifications

The catalog must dynamically adapt to:

- Guest
- Student
- Doctor
- Pharmacist
- Pharmacy
- Warehouse
- Trader
- Supplier

---

# 13. EMPLOYEE PORTAL

This is a critical part of the platform.

There will be internal employees / sales representatives who sell products and manage assigned customers.

Create a dedicated:

# EMPLOYEE PORTAL

Employees must NOT receive full Admin access.

Their permissions must be controlled by a dedicated employee role/permission system.

The Employee Portal should allow employees to see and manage only what they are authorized to access.

---

# 14. EMPLOYEE DASHBOARD

The employee dashboard must clearly show performance.

At minimum:

- Current month target
- Current month sales
- Remaining target
- Achievement percentage
- Number of orders
- Number of customers
- New customers
- Returns
- Gross sales
- Net sales
- Profit
- Commission / percentage earned
- Current estimated commission
- Previous months performance
- Target status

Example:

```text
Monthly Target:
100,000

Sales:
72,000

Achievement:
72%

Remaining:
28,000

Returns:
5,000

Net Sales:
67,000

Commission:
X%
```

The exact calculation must be configurable by Admin.

---

# 15. EMPLOYEE MONTHLY TARGET SYSTEM

Targets must be monthly and independently tracked.

Do NOT create a single permanent employee target.

Create a monthly target model/structure.

Example:

```text
Employee
    ↓
Target Period
    ↓
Year
    ↓
Month
    ↓
Target Amount
```

Example:

```text
Employee: Ahmed

January 2027
Target = 100,000

February 2027
Target = 120,000

March 2027
Target = 150,000
```

Each month must be a separate performance period.

Historical months must remain immutable or auditable after closing.

---

# 16. EMPLOYEE TARGET CONFIGURATION

Admin must be able to configure:

- Employee
- Target month
- Target year
- Target amount
- Target type
- Minimum achievement
- Commission percentage
- Bonus
- Rules
- Notes
- Status

Potential target types:

- Sales Amount
- Net Sales
- Gross Profit
- Number of Orders
- Number of Customers
- Product Category Sales
- Combined Target

The architecture should support multiple target types without requiring a rewrite.

---

# 17. EMPLOYEE SALES COMMISSION

Employees may have a percentage related to sales or profit.

The system must support configurable commission rules.

Examples:

```text
Sales:
100,000

Commission:
3%
```

Or:

```text
Gross Profit:
30,000

Commission:
10%
```

Or tiered:

```text
Achievement < 50%
Commission = 0%

50% - 79%
Commission = 1%

80% - 99%
Commission = 2%

100%+
Commission = 3%
```

Do NOT hard-code these rules.

Create a configurable Commission Engine.

---

# 18. EMPLOYEE PROFIT TRACKING

Employees may need visibility into:

- Sales
- Cost
- Gross profit
- Returns
- Net sales
- Net profit where applicable

The system must clearly distinguish:

```text
Revenue
Cost
Gross Profit
Returns
Discounts
Net Sales
Commission
```

Do not calculate "profit" using a simplistic formula if the business rules require a more accurate accounting model.

The architecture must support proper financial calculation.

---

# 19. RETURNS AND EMPLOYEE PERFORMANCE

Returns must be included in employee performance calculations according to configurable business rules.

Admin should be able to determine whether:

- Returns reduce sales
- Returns reduce target achievement
- Returns reduce commission
- Returns are attributed to the original employee
- Returns are attributed to the employee handling the return

Do not make these assumptions.

Design configurable rules.

---

# 20. EMPLOYEE CUSTOMER MANAGEMENT

Employees may have assigned customers.

An employee should be able to see authorized customer information such as:

- Customer name
- Customer type
- Phone
- Address where authorized
- Order history
- Total purchases
- Outstanding information if applicable
- Last order
- Assigned employee
- Customer status

Employees must NOT be able to access all customer data automatically.

Customer visibility must respect permissions and assignment rules.

---

# 21. CUSTOMER ASSIGNMENT

Support assigning customers to employees.

Potential relationships:

```text
Customer
    ↓
Primary Employee
```

or:

```text
Customer
    ↓
Sales Team
```

Design the architecture so that both models can be supported later if necessary.

Admin must be able to:

- Assign customer
- Reassign customer
- View employee customers
- Bulk assign
- Remove assignment
- Audit assignment changes

---

# 22. EMPLOYEE ORDER ATTRIBUTION

Orders may need to be attributed to an employee.

Possible sources:

- Employee-created order
- Customer-selected employee
- Assigned employee
- Referral
- Manual attribution by Admin

The system must define a clear order attribution strategy.

Avoid ambiguous commission ownership.

---

# 23. EMPLOYEE ORDER CREATION

Depending on permissions, employees may be allowed to create orders for customers.

If enabled, employee workflow may be:

```text
Employee
↓
Select Customer
↓
Browse Allowed Catalog
↓
Add Products
↓
Validate Access
↓
Validate Stock
↓
Apply Customer Pricing
↓
Create Order
```

Employees must NOT bypass:

- Product access policies
- Customer restrictions
- Pricing rules
- Stock rules
- Prescription rules
- Payment rules

---

# 24. EMPLOYEE CUSTOMER PRICING

Employees must not be allowed to arbitrarily change product prices unless explicitly permitted.

If discounts are allowed:

- Define discount limits
- Define approval requirements
- Log the discount
- Track who approved it
- Track the impact on profit and commission

---

# 25. EMPLOYEE PORTAL PERMISSIONS

Create granular permissions such as:

```text
employee.view_dashboard
employee.view_targets
employee.view_sales
employee.view_profit
employee.view_commission
employee.view_customers
employee.view_customer_orders
employee.create_order
employee.view_orders
employee.create_return
employee.view_returns
employee.apply_discount
employee.view_inventory
employee.view_products
employee.view_reports
```

Do not give all employees the same capabilities automatically.

---

# 26. EMPLOYEE ROLE LEVELS

Design for future employee roles such as:

- Sales Representative
- Senior Sales Representative
- Sales Manager
- Customer Service
- Warehouse Employee
- Inventory Employee
- Finance Employee
- Operations Employee

Each role must have permissions.

Do not hard-code permissions into frontend routes only.

---

# 27. EMPLOYEE MONTHLY PERFORMANCE

The Employee Portal must provide monthly history.

Example:

```text
2027
January
Target: 100,000
Sales: 95,000
Achievement: 95%
Commission: ...

February
Target: 120,000
Sales: 135,000
Achievement: 112.5%
Commission: ...

March
Target: 150,000
Sales: 160,000
Achievement: 106.7%
Commission: ...
```

Employees should see their own performance.

Managers/Admins may see broader performance based on permissions.

---

# 28. EMPLOYEE PERFORMANCE REPORTS

Admin should be able to compare employees.

Reports should support:

- Employee
- Month
- Year
- Sales
- Net Sales
- Profit
- Returns
- Target
- Achievement
- Commission
- New Customers
- Number of Orders

Support ranking:

- Top Sales
- Top Achievement %
- Top Profit
- Highest New Customers
- Lowest Returns

---

# 29. EMPLOYEE DASHBOARD SECURITY

An employee must never be able to manipulate:

- Target
- Commission percentage
- Profit
- Customer assignment
- Employee permissions
- Other employees' performance
- Product access policies
- Pricing rules

unless explicitly authorized.

All sensitive changes must be server-side protected.

---

# 30. USER TYPES

The system must support at least:

### Guest

### Student

### Doctor

### Pharmacist

### Pharmacy

### Warehouse

### Trader

### Supplier

### Employee

### Admin

Use scalable:

# RBAC + Permissions + Policy-Based Access Control

Do not rely on scattered hard-coded role checks.

---

# 31. PRODUCT ACCESS CONTROL

This is a critical security requirement.

Some products are public.

Some require login.

Some are restricted.

Examples:

### Public

Anyone may see and purchase.

### Registered

Login required.

### Student

Student-only.

### Doctor

Doctor-only.

### Pharmacist

Pharmacist-only.

### Pharmacy

Pharmacy-only.

### Warehouse

Warehouse-only.

### Trader

Trader-only.

### Professional Restricted

Only verified professionals.

---

# 32. SERVER-SIDE PRODUCT ACCESS

Frontend hiding is NOT security.

The backend API must enforce access.

Unauthorized users must not be able to:

- View
- Search
- Filter
- Add to wishlist
- Add to cart
- Checkout
- Purchase
- Access direct URLs
- Manipulate API requests to retrieve restricted products

Search and listing APIs must be policy-aware.

---

# 33. PRODUCT ACCESS POLICY ENGINE

Create a centralized Product Access Policy Engine.

Policies may evaluate:

- Authentication
- User type
- Role
- Permissions
- Verification status
- Professional verification
- Business verification
- Product classification
- Prescription requirement
- Customer eligibility
- Other configurable conditions

Return:

```text
ALLOW
DENY
```

Do not duplicate the same access logic across controllers, serializers, services, and frontend components.

---

# 34. VERIFICATION SYSTEM

Support verification statuses such as:

```text
Pending
Verified
Rejected
Suspended
Blocked
```

Applicable to:

- Doctors
- Pharmacists
- Pharmacies
- Suppliers
- Warehouses
- Traders where required

Restricted products may require:

```text
User Type
+
Verified Status
+
Required Permission
```

---

# 35. ADMIN PRODUCT ACCESS MATRIX

Admin should be able to control product visibility/access.

Example:

| Product | Guest | Student | Doctor | Pharmacist | Pharmacy | Warehouse | Trader |
|---|---:|---:|---:|---:|---:|---:|---:|
| Product A | YES | YES | YES | YES | YES | YES | YES |
| Product B | NO | NO | YES | YES | YES | NO | NO |
| Product C | NO | NO | NO | YES | YES | NO | NO |

The actual implementation must be more flexible than a fixed matrix.

---

# 36. DYNAMIC CATALOG

The catalog must adapt to the authenticated user.

Guest:

```text
Public Products
```

Student:

```text
Public
+
Student
```

Doctor:

```text
Public
+
Doctor
+
Professional
```

Pharmacy:

```text
Public
+
Pharmacy
+
Wholesale
+
Professional
+
Allowed Restricted Products
```

The backend determines what is available.

---

# 37. ADMIN PREVIEW MODE

Admin should be able to preview the store as:

- Guest
- Student
- Doctor
- Pharmacist
- Pharmacy
- Warehouse
- Trader
- Supplier
- Employee

This is important for testing access policies and user experiences.

---

# 38. PHARMACEUTICAL MODULE

Pharmaceutical products require specialized handling.

Support:

- Generic name
- Brand name
- Active ingredients
- Strength
- Dosage form
- Pack size
- Manufacturer
- Registration information
- Prescription requirement
- Storage conditions
- Batch number
- Expiry date
- Regulatory information
- Restrictions

Do not treat all medicines as ordinary ecommerce products.

The architecture must be prepared for applicable local regulatory requirements.

---

# 39. PRESCRIPTION WORKFLOW

For prescription-required products:

```text
Customer
↓
Upload Prescription
↓
Professional Review
↓
Approved / Rejected
↓
Order Processing
```

Store:

- Reviewer
- Decision
- Date
- Reason
- Audit trail

Prescription files must be securely protected.

---

# 40. INVENTORY ARCHITECTURE

Do not use a simple stock integer as the entire inventory system.

Support:

- Physical Stock
- Reserved Stock
- Available Stock
- Damaged Stock
- Expired Stock

Inventory transactions:

- Purchase
- Sale
- Return
- Adjustment
- Damage
- Expired
- Reservation
- Reservation Release
- Transfer

Prevent overselling using proper transaction/concurrency controls.

---

# 41. BATCH MANAGEMENT

For applicable products, support:

- Batch Number
- Manufacturing Date
- Expiry Date
- Quantity
- Cost
- Selling Price
- Supplier
- Warehouse

Support:

# FEFO — First Expire, First Out

---

# 42. LOW STOCK SYSTEM

Each applicable product may have:

- Reorder Level
- Critical Level
- Maximum Level

Example:

```text
100 = normal
20 = low stock
5 = critical
0 = out of stock
```

Admin must receive alerts.

Avoid notification spam using deduplication/cooldown logic.

---

# 43. OUT OF STOCK

When stock reaches zero:

```text
Out of Stock
```

Do not delete the product.

For public products, support:

# Notify Me When Available

For restricted products, preserve the same access policies.

---

# 44. STUDENT EXPERIENCE

Students are the initial growth market.

Support:

```text
University
    ↓
Faculty
    ↓
Department
    ↓
Academic Year
    ↓
Required Products
    ↓
Recommended Products
```

Support:

- Student bundles
- Faculty bundles
- Semester bundles
- Required equipment
- Recommended equipment
- Student pricing
- Student discounts
- University-specific catalogs

---

# 45. REFERRAL SYSTEM

Support:

- Referral code
- Referral link
- Referral reward
- First-order reward
- Referral statistics
- Anti-abuse protection

Prevent:

- Self-referral
- Fake accounts
- Duplicate rewards
- Abuse

---

# 46. CAMPUS AMBASSADOR

Design for future:

# Campus Ambassador

Support:

- Referral code
- Referral link
- Dashboard
- Referral statistics
- Orders generated
- Rewards
- Commission / points

---

# 47. PHARMACY B2B

Pharmacies need a professional B2B portal.

Support:

- Business profile
- Verification
- Orders
- Invoices
- Purchase history
- Quick reorder
- Wholesale pricing
- Discounts
- Loyalty points
- Account statements
- Documents

---

# 48. LOYALTY ENGINE

Create a configurable loyalty engine.

Support:

- Points earned
- Points redeemed
- Points expired
- Loyalty transactions
- Customer tiers
- Rewards

Example:

```text
Bronze
Silver
Gold
Platinum
```

Do not hard-code thresholds.

---

# 49. PRICING ENGINE

Support:

- Normal Price
- Student Price
- Doctor Price
- Pharmacy Price
- Wholesale Price
- Customer-specific Price
- Volume Pricing
- Promotions
- Coupons
- Loyalty Discounts

Create a centralized pricing engine.

Do not scatter pricing calculations across controllers or frontend components.

---

# 50. CART & CHECKOUT

At checkout, revalidate:

- Authentication
- Product access
- Verification
- Product availability
- Stock
- Price
- Discounts
- Coupons
- Shipping
- Payment
- Prescription requirements
- Customer eligibility

Never trust frontend calculations.

---

# 51. ORDER ARCHITECTURE

Define a robust order lifecycle.

Possible states:

```text
Draft
Pending Payment
Paid
Confirmed
Processing
Ready for Shipping
Shipped
Delivered
Cancelled
Returned
Refunded
```

Define valid state transitions.

Do not allow invalid transitions.

---

# 52. ORDER ATTRIBUTION

Orders may be associated with:

- Customer
- Employee
- Sales representative
- Assigned employee
- Referral
- Campus Ambassador
- Supplier
- Warehouse

Define an unambiguous attribution model.

This is critical for employee commissions and performance.

---

# 53. EMPLOYEE COMMISSION VS ORDER ATTRIBUTION

Clearly separate:

- Who created the order
- Who owns the customer
- Who generated the sale
- Who receives commission
- Who handled the return

Do not assume these are always the same person.

Design explicit fields/relationships and configurable business rules.

---

# 54. PAYMENT ARCHITECTURE

Do not hard-code a single payment provider.

Create a Payment Gateway abstraction supporting future:

- Card
- Wallet
- Bank Transfer
- Cash on Delivery
- Other gateways

Orders must not directly depend on a specific gateway.

---

# 55. SHIPPING

Create an independent shipping module.

Support:

- Addresses
- Zones
- Governorates
- Shipping fees
- Delivery methods
- Shipments
- Tracking numbers
- Delivery status

Prepare for future integrations with shipping providers.

---

# 56. NOTIFICATIONS

Create a reusable notification engine.

Events include:

- Low Stock
- Critical Stock
- Out of Stock
- Expiry Warning
- Product Expired
- New Order
- Payment
- Shipment
- Order Cancellation
- Pharmacy Verification
- Prescription Review
- Loyalty Reward
- Referral Reward
- Employee Target Progress
- Employee Target Achievement
- Employee Target Missed
- Commission Update
- Customer Assignment
- Employee announcements

Support future channels:

- In-App
- Email
- SMS
- WhatsApp
- Push Notifications

---

# 57. AUDIT LOGGING

Track sensitive operations:

- Price changes
- Stock changes
- Product access policy changes
- User role changes
- Permission changes
- Pharmacy verification
- Prescription decisions
- Refunds
- Inventory adjustments
- Order status changes
- Employee target changes
- Commission rule changes
- Customer assignment changes
- Employee permission changes

Record when appropriate:

- User
- Action
- Object
- Old value
- New value
- Timestamp
- IP
- Request metadata

---

# 58. API-FIRST ARCHITECTURE

The system must be API-first.

Example:

```text
/api/v1/auth/
/api/v1/users/
/api/v1/products/
/api/v1/categories/
/api/v1/inventory/
/api/v1/cart/
/api/v1/orders/
/api/v1/payments/
/api/v1/pharmacies/
/api/v1/suppliers/
/api/v1/employees/
/api/v1/targets/
/api/v1/commissions/
/api/v1/customers/
/api/v1/loyalty/
/api/v1/referrals/
/api/v1/notifications/
/api/v1/admin/
```

The actual API structure should be decided after auditing the existing backend.

Do not create redundant endpoints if existing APIs can be extended cleanly.

---

# 59. API SECURITY

All sensitive business rules must be enforced by the backend.

Never rely on:

- Frontend route guards
- Hidden buttons
- Hidden menus
- Disabled inputs
- Client-side role checks

Frontend checks are for UX only.

Backend checks are authoritative.

---

# 60. API DOCUMENTATION

Use OpenAPI / Swagger where appropriate.

Every endpoint should document:

- Authentication
- Permissions
- Request
- Response
- Validation
- Errors
- Pagination
- Filtering
- Sorting

---

# 61. DATABASE ARCHITECTURE

Design a proper relational model.

Provide:

- Models
- Relationships
- Foreign Keys
- Constraints
- Unique Constraints
- Indexes
- Soft Delete Strategy
- Audit Strategy

Pay special attention to:

- Users
- Customers
- Employees
- Employee targets
- Employee commissions
- Customer assignments
- Products
- Product access policies
- Pricing
- Inventory
- Batches
- Orders
- Order attribution
- Payments
- Returns
- Loyalty
- Referrals
- Pharmacies
- Verification

---

# 62. EMPLOYEE DATA MODEL REQUIREMENTS

The architecture should support concepts equivalent to:

```text
Employee
EmployeeRole
EmployeePermission
EmployeeTarget
EmployeeTargetPeriod
CommissionRule
CommissionTransaction
CustomerAssignment
SalesAttribution
EmployeePerformanceSnapshot
```

Do not blindly create these exact models without evaluating the existing project.

Determine whether existing models can be reused or extended.

---

# 63. EMPLOYEE TARGET PERIOD

Each target must belong to a defined period.

At minimum:

```text
year
month
start_date
end_date
```

The system must support:

- Draft
- Active
- Closed
- Archived

A closed period should not be silently recalculated without an audit trail.

---

# 64. COMMISSION CALCULATION

Commission calculation must be deterministic and auditable.

For every commission result, be able to explain:

```text
Employee
Period
Orders Included
Gross Sales
Returns
Net Sales
Cost
Profit
Achievement
Commission Rule
Commission Rate
Commission Amount
```

Avoid black-box calculations.

---

# 65. FINANCIAL PRECISION

Use proper monetary types and calculations.

Do not use floating-point arithmetic for money.

Define:

- Currency
- Decimal precision
- Rounding rules
- Tax treatment where applicable
- Discount treatment
- Return treatment
- Commission treatment

Do not invent tax/regulatory rules; identify them as configurable requirements where needed.

---

# 66. EMPLOYEE REPORTING

Admin reports:

- Monthly sales
- Net sales
- Profit
- Returns
- Target
- Achievement
- Commission
- New customers
- Orders
- Average order value

Employee sees only authorized scope.

Manager sees team scope.

Admin sees global scope.

---

# 67. SEARCH

Search should support:

- Product name
- Brand
- Generic name
- SKU
- Barcode
- Category
- Manufacturer
- Active ingredient
- University
- Faculty

Search must respect product access policies.

---

# 68. FILTERING

Support:

- Category
- Brand
- Price
- Availability
- Manufacturer
- University
- Faculty
- Product type
- Prescription requirement
- Rating
- Discount

Access filtering must happen server-side.

---

# 69. PERFORMANCE

Audit the current project for:

- N+1 queries
- Slow APIs
- Excessive database queries
- Missing indexes
- Oversized API responses
- Oversized frontend bundles
- Unnecessary rerenders
- Duplicated state
- Duplicate API calls
- Poor caching
- Inefficient serialization

Reuse existing optimizations.

Do not optimize blindly.

---

# 70. BACKGROUND JOBS

Design for background processing where appropriate:

- Notifications
- Emails
- Stock alerts
- Expiry alerts
- Loyalty calculations
- Commission calculations
- Reports
- Analytics
- Image processing

Do not introduce infrastructure unnecessarily if the existing architecture has an appropriate solution.

---

# 71. FILE MANAGEMENT

Support:

- Product images
- Pharmacy documents
- Verification documents
- Prescriptions
- Employee documents where necessary

Sensitive files must not be public.

Use:

- File type validation
- Size limits
- Secure storage
- Access control
- Authorization checks

---

# 72. PRODUCT REVIEWS

Support:

- Rating
- Review
- Verified purchase
- Images if appropriate
- Moderation

---

# 73. WISHLIST

Support:

- Add
- Remove
- Availability
- Back-in-stock notification
- Price-drop notification

All access policies still apply.

---

# 74. COUPONS & PROMOTIONS

Support:

- Percentage discount
- Fixed discount
- Minimum order
- Maximum discount
- Expiry
- Usage limits
- Customer limits
- Product restrictions
- Category restrictions
- Pharmacy restrictions
- Student restrictions
- Employee-created order restrictions where appropriate

Define discount precedence centrally.

---

# 75. REPORTING & ANALYTICS

Support:

- Sales
- Product sales
- Category sales
- Pharmacy purchases
- Student purchases
- Employee performance
- Supplier sales
- Inventory
- Expiry
- Profit
- Loyalty
- Referral
- Customer behavior

Analytics should support future:

- Demand forecasting
- Inventory forecasting
- Product recommendations
- Customer segmentation

---

# 76. MULTI-UNIVERSITY

Do not hard-code one university.

Use:

```text
University
    ↓
Faculty
    ↓
Department
    ↓
Academic Year
```

The platform must be able to expand to multiple universities.

---

# 77. FUTURE MARKETPLACE

Design for:

```text
Platform
    ↓
Suppliers
    ↓
Warehouses
    ↓
Products
    ↓
Customers
```

A product may eventually be offered by multiple suppliers.

Do not necessarily implement full marketplace behavior in Phase 1.

---

# 78. MULTI-LANGUAGE REQUIREMENT

The entire system must be bilingual from the backend.

Required languages:

```text
Arabic
English
```

This is NOT just a frontend translation requirement.

The backend must be designed with complete localization support.

---

# 79. BACKEND BILINGUAL REQUIREMENT

The backend must support Arabic and English for user-facing content where appropriate.

This includes, where applicable:

- Product names
- Product descriptions
- Categories
- Subcategories
- Brands
- Product attributes
- Educational content
- Notifications
- Email templates
- SMS/WhatsApp templates where supported
- Error messages
- Validation messages
- System messages
- Admin-configurable content
- Reports where user-facing labels are generated by backend
- API metadata where localization is required

Do not create separate databases for each language.

Use a proper localization/translation strategy.

Evaluate whether the existing project already has an i18n/localization architecture and reuse it.

---

# 80. API LANGUAGE NEGOTIATION

The API should be able to determine language using a clear priority strategy.

Evaluate the existing system first.

A possible strategy:

```text
Explicit request language
↓
Authenticated user's preferred language
↓
Profile / organization preference
↓
Language header
↓
Session/cookie where applicable
↓
System default
↓
Arabic fallback
```

Do not implement this blindly if the existing project already has a better architecture.

Document the final strategy.

---

# 81. BILINGUAL ERROR RESPONSES

API errors should support Arabic and English.

For example, conceptually:

```json
{
  "code": "INSUFFICIENT_STOCK",
  "message": "...",
  "detail": "..."
}
```

The response should be localizable according to the requested language.

Prefer stable machine-readable error codes with localized human-readable messages.

Do not make frontend logic depend on English error text.

---

# 82. BILINGUAL NOTIFICATIONS

Notifications must support Arabic and English.

Do not hard-code only one language.

Templates should support localized variants.

Example:

```text
Low Stock Alert
Arabic Template
English Template
```

---

# 83. BILINGUAL EMAILS

Email templates must support:

- Arabic
- English

The selected language should be determined by the appropriate recipient/user preference.

---

# 84. BILINGUAL ADMIN CONTENT

Admin-configurable content that is displayed to customers should support Arabic and English where appropriate.

Examples:

- Product descriptions
- Category descriptions
- Promotional banners
- Notifications
- Offers
- Marketing text

The architecture should distinguish:

### UI translations

from:

### Business/content translations

---

# 85. RTL / LTR

Arabic requires RTL.

English requires LTR.

The frontend must dynamically support both.

The backend must provide language metadata needed by the frontend.

Do not hard-code layout direction into individual components.

---

# 86. INTERNATIONALIZATION QUALITY

Audit the existing frontend and backend for:

- Hard-coded English text
- Hard-coded Arabic text
- Mixed-language labels
- Non-localized validation messages
- Date formatting
- Number formatting
- Currency formatting
- RTL issues
- Translation duplication

Use existing localization infrastructure whenever possible.

---

# 87. CURRENCY

Do not assume the store can only support one currency.

Evaluate the existing architecture.

Design for future multi-currency support if it can be done cleanly without unnecessary complexity.

At minimum:

- Currency
- Decimal precision
- Price formatting
- Localization

should be architecturally isolated from business logic.

---

# 88. SECURITY REVIEW

Perform a full security review.

Check:

- Authentication
- Authorization
- IDOR
- Privilege escalation
- Insecure direct object access
- Product access bypass
- Order access bypass
- Employee data leakage
- Customer data leakage
- Prescription file exposure
- Verification document exposure
- File upload vulnerabilities
- Rate limiting
- API throttling
- Token security
- Password security
- Sensitive data handling
- Audit logging

---

# 89. TESTING STRATEGY

Create a comprehensive test strategy.

Include:

### Unit Tests

### API Tests

### Authentication Tests

### Permission Tests

### Product Access Tests

### Inventory Tests

### Pricing Tests

### Cart Tests

### Order Tests

### Payment Tests

### Loyalty Tests

### Referral Tests

### Prescription Tests

### Employee Target Tests

### Commission Tests

### Customer Assignment Tests

### Localization Tests

### Concurrency Tests

Critical security tests:

### Unauthorized Product Access

### Unauthorized Employee Data Access

### Unauthorized Customer Data Access

### Overselling Prevention

---

# 90. FRONTEND PORTAL ARCHITECTURE

Determine whether the existing frontend can support multiple portals cleanly.

Possible structure:

```text
Admin Portal
Customer Portal
Store
Employee Portal
```

Do not duplicate:

- Authentication
- UI components
- API client
- Tables
- Forms
- Notifications
- Layout primitives

Create shared infrastructure where appropriate.

---

# 91. EMPLOYEE PORTAL UX

The employee portal should prioritize:

- Sales performance
- Target progress
- Customers
- Orders
- Returns
- Commission
- Profit visibility where authorized
- Quick actions

It should be simpler than the Admin Portal.

Employees should not see unrelated system administration functionality.

---

# 92. ADMIN PREVIEW FOR EMPLOYEE

Admin should be able to preview the Employee Portal according to an employee's permissions.

This helps test:

- Employee roles
- Employee permissions
- Customer visibility
- Target visibility
- Commission visibility

---

# 93. MIGRATION PRINCIPLE

Prefer:

# Incremental Evolution

over:

# Big Bang Rewrite

Unless the existing architecture is fundamentally unusable.

If something must be rewritten, explain why.

---

# 94. FRONTEND MIGRATION PLAN

Create a specific migration plan for `full-temp/`.

For every important existing page/component:

```text
Current Component
↓
Keep?
↓
Refactor?
↓
Replace?
↓
Move?
↓
Delete?
```

Reference actual paths.

Example:

```text
full-temp/src/components/ProductCard.jsx
→ REUSE + REFACTOR

Reason:
Existing component is reusable but lacks:
- Access-aware state
- Stock state
- User-specific pricing
- Restricted product handling
```

Do this using actual repository files.

---

# 95. DO NOT DUPLICATE EXISTING COMPONENTS

If the existing project already has:

- Modal
- Table
- Form
- Button
- Card
- Layout
- Sidebar
- Notification
- Toast
- Pagination
- Search
- Filters
- API client
- Authentication
- Charts
- Date pickers

do NOT create another version without a strong reason.

Extend shared components.

---

# 96. DO NOT DUPLICATE BUSINESS LOGIC

Before implementing any feature, search the repository for existing related logic.

Examples:

Before creating ProductService:

Search for existing product logic.

Before creating InventoryService:

Search for existing inventory logic.

Before creating NotificationService:

Search for existing notification logic.

Before creating EmployeeService:

Search for existing employee/staff logic.

Before creating CustomerAssignment:

Search for existing customer/staff relationships.

Reuse or refactor where appropriate.

---

# 97. ADMIN CONFIGURABILITY

Business rules must not be unnecessarily hard-coded.

Admin should eventually be able to configure:

- Product access policies
- Low stock levels
- Loyalty rules
- Referral rewards
- Pharmacy tiers
- Student discounts
- Employee targets
- Commission rules
- Discount limits
- Shipping rules
- Coupon rules
- Notification rules
- Language settings

---

# 98. PERFORMANCE AND SCALABILITY

The platform must be designed to grow.

Potential future scale:

```text
10,000 users
100,000 users
1,000,000+ users
```

Evaluate:

- Database indexing
- Caching
- Pagination
- Query optimization
- Background jobs
- API response size
- Frontend bundle size
- Search architecture
- File storage
- Notification architecture

Do not prematurely over-engineer.

---

# 99. DEVELOPMENT PHASES

Create a realistic roadmap.

At minimum evaluate:

## Phase 0
Discovery & Architecture

## Phase 1
Foundation & Authentication

## Phase 2
Users / Roles / Permissions / Verification

## Phase 3
Catalog & Products

## Phase 4
Product Access Policies

## Phase 5
Inventory & Batches

## Phase 6
Cart & Orders

## Phase 7
Payments & Shipping

## Phase 8
Student Store

## Phase 9
Pharmacy B2B

## Phase 10
Employee Portal

## Phase 11
Employee Targets & Commission

## Phase 12
Loyalty

## Phase 13
Referral / Campus Ambassador

## Phase 14
Notifications

## Phase 15
Analytics / Reporting

## Phase 16
Supplier System

## Phase 17
Marketplace

You must change this order if your analysis shows a better dependency sequence.

---

# 100. PHASE DEFINITION

For every implementation phase provide:

- Objective
- Business value
- Files/modules affected
- Database changes
- API changes
- Frontend changes
- Existing code reused
- Existing code refactored
- New code required
- Dependencies
- Tests
- Risks
- Rollback strategy
- Definition of Done

---

# 101. QUALITY GATES

Before moving to the next phase, define a quality gate.

Examples:

```text
Database migrations pass
API tests pass
Permission tests pass
Access-policy tests pass
Employee tests pass
Frontend build passes
Localization tests pass
No critical errors
No regression in existing features
```

---

# 102. WHAT YOU MUST DELIVER BEFORE CODING

After inspecting the entire repository, produce a document called:

# MASTER IMPLEMENTATION PLAN

It must contain:

## 1. Executive Summary

## 2. Current System Overview

## 3. Current Architecture

## 4. Frontend Audit

## 5. Backend Audit

## 6. `full-temp/` Reuse Analysis

## 7. Reuse / Refactor / Rebuild / Remove / New Matrix

## 8. Technical Debt

## 9. Architecture Gaps

## 10. Target Architecture

## 11. Portal Architecture

## 12. Domain Architecture

## 13. Database Architecture

## 14. ERD

## 15. API Architecture

## 16. Authentication Architecture

## 17. RBAC & Permission Architecture

## 18. Product Access Policy Architecture

## 19. Product Visibility Architecture

## 20. Inventory Architecture

## 21. Pharmaceutical Architecture

## 22. Pricing Architecture

## 23. Order Architecture

## 24. Pharmacy B2B Architecture

## 25. Employee Portal Architecture

## 26. Employee Target Architecture

## 27. Commission Architecture

## 28. Customer Assignment Architecture

## 29. Loyalty Architecture

## 30. Referral Architecture

## 31. Notification Architecture

## 32. Payment Architecture

## 33. Shipping Architecture

## 34. Localization Architecture

## 35. Arabic / English Backend Strategy

## 36. Admin Portal

## 37. Customer Portal

## 38. Online Store

## 39. Employee Portal

## 40. Security Architecture

## 41. Testing Strategy

## 42. Performance Strategy

## 43. Deployment Strategy

## 44. Migration Strategy

## 45. Implementation Phases

## 46. Risks

## 47. Recommendations

## 48. What Should NOT Be Built Yet

## 49. Final Recommended Plan

---

# 103. REQUIRED FILE-LEVEL ANALYSIS

Do not stop at architecture diagrams.

Reference actual files from the repository.

For important existing code, state:

```text
File:
Purpose:
Current Behavior:
Dependencies:
Reusable:
Required Changes:
Risk:
Recommendation:
```

This is especially important for:

- Authentication
- Layouts
- Product components
- API clients
- State management
- Dashboard components
- Forms
- Tables
- Existing user management
- Existing employee/staff functionality
- Existing customer functionality
- Existing localization
- Existing notifications

---

# 104. BUSINESS RULE IDENTIFICATION

Before implementation, explicitly list all business rules that still require confirmation.

Examples:

- Employee commission calculation
- Return effect on commission
- Return effect on target
- Profit calculation
- Customer assignment
- Order attribution
- Employee discount limits
- Pharmacy verification
- Prescription requirements
- Restricted product rules
- Loyalty points
- Referral rewards
- Currency
- Taxes
- Shipping
- Payment methods

Do NOT silently invent business rules.

Where a rule is unknown:

1. Identify it.
2. Explain the options.
3. Recommend a default.
4. Mark it as requiring business approval.

---

# 105. IMPORTANT: REGULATORY AWARENESS

The system involves pharmaceutical and potentially restricted medical products.

The architecture must support applicable laws, licensing requirements, prescription restrictions, product restrictions, record keeping, and other regulatory requirements.

Do not claim that a workflow is legally compliant without verification.

Where regulations are unknown:

- Mark the requirement.
- Make the system configurable.
- Avoid hard-coding assumptions.

---

# 106. NO CODE DURING THIS PHASE

Until explicit approval:

DO NOT:

- Create files
- Modify files
- Delete files
- Rename files
- Install packages
- Run migrations
- Change database schema
- Refactor code
- Rewrite components
- Implement APIs
- Implement models
- Modify configuration

The only exception is read-only inspection commands needed to understand the repository.

---

# 107. READ-ONLY DISCOVERY COMMANDS

You may use safe/read-only commands to inspect the repository.

Examples:

```bash
pwd
ls
find
tree
cat
sed
grep
rg
git status
git log
```

Use equivalent commands appropriate for the environment.

Do not execute destructive commands.

---

# 108. FINAL STOP CONDITION

After completing the full analysis:

# STOP.

Do not implement anything.

Wait for explicit approval.

The next instruction will determine whether to:

- Modify the existing architecture
- Implement Phase 1
- Implement a specific module
- Refactor an existing module
- Build APIs
- Build frontend portals

---

# 109. FINAL PRINCIPLE

The goal is NOT to generate the largest amount of code.

The goal is to create the **best architecture with the least unnecessary rewriting**.

Reuse what is good.

Refactor what is close.

Replace only what is fundamentally wrong.

Build only what is missing.

Keep business logic in the backend.

Keep APIs secure.

Keep product restrictions enforced server-side.

Keep employee information protected.

Keep financial calculations auditable.

Keep targets monthly and historically traceable.

Keep commission calculations deterministic and explainable.

Keep Arabic and English supported from the backend.

Keep the frontend reusable.

Keep the platform scalable.

The initial product is:

# UNIVERSITY MEDICAL STORE

The future product is:

# LARGE B2C + B2B + EMPLOYEE SALES + MARKETPLACE MEDICAL COMMERCE PLATFORM

Your first deliverable is therefore NOT CODE.

Your first deliverable is:

# A COMPLETE, EVIDENCE-BASED MASTER IMPLEMENTATION PLAN BASED ON THE ACTUAL EXISTING REPOSITORY.
