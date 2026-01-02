# 🛸 EVE Master Scanner v12.0

A powerful EVE Online market analysis tool built with Python and Gradio. This application helps traders identify profitable opportunities across major trade hubs and provides automation for continuous market monitoring.

## 🌟 Key Features

- **💰 Trade Mode (Jita)**: 
  - Real-time spread analysis between Buy and Sell orders.
  - ROI filtering (10% to 300%).
  - Historical volume/price verification to avoid market manipulation.
- **🚛 Import Mode (Hubs)**:
  - Comparison between Jita sell prices and regional hub prices.
  - "Empty Market" detection for high-margin opportunities.
  - Support for hubs like Curse (G-0Q86) and Amarr.
- **🔄 Automation**:
  - Cyclical scanning with configurable intervals.
  - Automatic CSV report generation.
  - Multi-threaded market data fetching via ESI API.

## 🛠️ Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd eve-apps
   ```

2. **Install dependencies**:
   ```bash
   pip install gradio requests pandas
   ```

## 🚀 Usage

Run the main application:
```bash
python market-app.py
```
This will launch a Gradio interface in your browser (usually at `http://127.0.0.1:7860`).

### Configuration
- **Min Vol/Day**: Minimum average daily volume over the last 30 days.
- **Scan Depth**: Number of ESI pages to scan (0 = all pages).
- **Min ROI**: Minimum Return on Investment percentage for imports.

## 📂 Project Structure

- `market-app.py`: Main application script and UI.
- `reports/`: Automatically generated CSV reports from scans.
- `eve-jita-data/`: Cached or processed Jita market data.
- `.gitignore`: Configured to exclude generated reports and Python environment files.

## ⚠️ Disclaimer
This tool uses EVE Online's ESI API. Ensure your User-Agent is correctly configured in the `HEADERS` section of `market-app.py` if you modify the code.
