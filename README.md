# RBS Secure Review System 🏥📊

A secure, Streamlit-based web application designed for managing and evaluating the Dr Ranjeet Bhagwan Singh Medical Research Grant applications.

## 🌟 Features
* **Role-Based Access Control**: Separate interfaces for `Admin` and `Reviewer` roles.
* **Secure Authentication**: Passwords are cryptographically hashed using `bcrypt`.
* **Admin Dashboard**: Real-time KPI metrics, interactive data visualizations (Plotly), and PDF/CSV reporting.
* **Reviewer Portal**: Clean interface for reviewing applicants, saving progress, and editing past submissions via pop-up dialogs.
* **Database Self-Healing**: Automatically generates missing PostgreSQL tables and columns on startup.

## 🛠️ Tech Stack
* **Frontend/Backend**: Python, Streamlit
* **Database**: PostgreSQL, SQLAlchemy, psycopg2
* **Analytics**: Pandas, Plotly Express
* **Exports**: FPDF, Kaleido (for chart-to-PDF generation)

## 🚀 How to Run Locally

1. **Clone the repository**
   ```bash
   git clone [https://github.com/YOUR_USERNAME/rbs_review_system.git](https://github.com/YOUR_USERNAME/rbs_review_system.git)
   cd rbs_review_system
