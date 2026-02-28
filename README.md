Real Estate Deal Analyzer:
A configurable command-line tool that screens property listings and performs automated rental property underwriting using cap rate, cash-on-cash return, DSCR, and buy-box criteria.
Built for fast deal analysis and market filtering using a data-driven workflow.

Features:
📊 - Automated deal underwriting
🧮 - Cap rate, Cash-on-Cash, DSCR calculation
🏷 - Buy-box filtering (price, beds, sqft, market, etc.)
💰 - Configurable financing assumptions
🏠 - Rent estimation engine with multiple strategies
📈 - Ranked output of top investment opportunities
🧠 - Underwriting Metrics
⚙ - Fully configurable via YAML
⚠ -  Manual review detection for borderline deals

The analyzer computes:
* Net Operating Income (NOI)
* Cap Rate
* Cash-on-Cash Return
* DSCR
* Annual Cash Flow
* Total Cash Invested

🗂 Project Structure
.
├── analyze_listings.py   # Main CLI underwriting engine
├── config.yml           # Buy box + financing + rent model
├── listings.csv         # Input dataset
├── results.csv          # Output (generated)
├── requirements.txt
└── .gitignore

⚙ Configuration
All investment assumptions are defined in:
config.yml

This includes:
- Buy box criteria
- Financing terms
- Expense ratios
- Target return thresholds
- Rent estimation strategy
This makes the model reusable across different markets and strategies.

📥 Input Data
Accepts:
CSV
JSON (array of listings)

Required fields:
- price
- address
- city
- state
- Optional fields (improve accuracy):
- beds
- baths
- sqft
- lot_sqft
- year_built
- hoa_monthly
- taxes_annual

▶ Usage
Run from the project root:
python analyze_listings.py --config config.yml --input listings.csv --out results.csv

📤 Output
The tool generates:
results.csv

Top deals are ranked by:
- Meets investment targets
- Cap rate
- Cash-on-cash return

Console preview example:
Top candidates:
Address | Price | Rent | Cap Rate | CoC | DSCR | Meets Target
🧮 Rent Estimation Strategies
The rent engine uses a layered approach:
Manual override
Rule-of-thumb by bedroom count
Rent-to-price ratio
Each estimate includes a confidence score.

🎯 Buy Box Filtering
Example:
Market: Sacramento, CA
Max price: $650k
Min beds: 3
Min sqft: 1100
Property type: SFR / Townhouse / Duplex

⚠ Manual Review Detection
Deals are flagged when:
Returns are near target thresholds
Rent estimate confidence is low
Key property data is missing

🛠 Tech Stack
Python
Pandas
PyYAML
argparse

📈 Example Use Cases
Rental property screening
BRRRR deal analysis
Market scanning for investors
Data-driven acquisition pipelines

🔮 Roadmap
Future improvements:
Zillow/Redfin API integration
Predictive rent model 
Portfolio aggregation
Sensitivity analysis
Develop full pipeline

👤 Author
Built as a data-driven real estate investment analysis tool.

⭐ Resume / Portfolio Value
This project demonstrates:
Config-driven system design
Financial modeling
Data pipeline workflow
CLI tool development
Real-world analytics application

Looking for:
Data Engineering
Analytics Engineering
FinTech / PropTech roles

