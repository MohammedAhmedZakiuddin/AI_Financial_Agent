# 💰 JP Morgan Chase – AI Financial Assistant

Welcome to the **AI Financial Assistant**, a virtual assistant built using OpenAI and Gradio to streamline customer support at financial institutions like JP Morgan Chase.

> **From wait-times to real-time — an OpenAI-powered customer experience**

---

## 🚀 Project Overview

This assistant helps both **existing customers** and **new users** by offering:

- 📞 Phone + ZIP verification for existing customers  
- 💼 AI support for banking queries (balance, recent transactions, savings products)  
- 📄 Intelligent PDF document upload and analysis (e.g., 10-K, 10-Q)  
- 🧠 GPT-powered Q&A on uploaded documents  
- 📬 New customer lead capture flow (name → phone → email)

---

## 📂 Tech Stack

| Tool      | Purpose                                 |
|-----------|------------------------------------------|
| 🧠 OpenAI | Natural Language Processing (GPT-3.5)     |
| 🖼️ Gradio | Web-based Chat UI                         |
| 🐍 Python | Core logic & data processing              |
| 🗃️ SQLite | Lightweight backend database              |
| 📄 pdfplumber | PDF content extraction                |
| 🌐 GitHub Pages | Deployment (static site hosting)    |

---

## 🛠️ Setup Instructions

1. **Clone the Repository**
   ```bash
   git clone https://github.com/yourusername/ai-financial-agent.git
   cd ai-financial-agent
   pip install -r requirements.txt
2. python financial_ai_agent.py

## 🧩 Database Schema

The project uses two SQLite tables:

- `customers`: Stores customer profiles with `id`, `first_name`, `last_name`, `phone`, `zip_code`, and `balance`.
- `transactions`: Contains transaction logs linked to `customer_id`.

This enables the dynamic fetching and display of balance checks and transaction history.

---

## 🌱 Future Enhancements

- ✅ Multi-file PDF upload  
- 📊 Financial trend graphs from uploaded reports  
- 🧾 Tax document summaries  
- 🔗 API Integration with Chase's real backend  

---

## 👨‍🎓 Author

**Mohammed Zakiuddin**  
Master's Student, Data Science  
Texas A&M University

---

## 📬 Contact

If you have any questions or suggestions, feel free to [open an issue](https://github.com/MohammedAhmedZakiuddin/ai-financial-agent/issues) or email me at  
[ahmedzaki372100@gmail.com].


