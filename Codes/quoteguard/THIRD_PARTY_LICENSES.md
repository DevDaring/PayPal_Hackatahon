# Third-party licenses

Licenses read from installed package metadata on 31 Oct 2026. All are used unmodified as dependencies.

| Component | License |
|---|---|
| FastAPI, SQLAlchemy, Alembic, Pydantic, pydantic-settings, LangGraph, pdfplumber | MIT |
| httpx, uvicorn, pypdf | BSD-3-Clause |
| pypdfium2 (bundles PDFium) | Apache-2.0 / BSD-3-Clause |
| ReportLab (open-source toolkit) | BSD |
| psycopg 3 | LGPL-3.0-only — used as an unmodified, dynamically imported library |
| React, React DOM, React Router, TanStack Query, Tailwind CSS, Vite, sonner | MIT |
| AG Grid Community (`ag-grid-community`, `ag-grid-react`) | MIT — no Enterprise features or license key used |
| `@paypal/react-paypal-js` | Apache-2.0 |
| Lucide icons | ISC |
| Inter, Instrument Serif fonts (Fontsource) | SIL Open Font License 1.1 |
| PostgreSQL | PostgreSQL License |

Illustrations in `frontend/public/illustrations/` and `submission/assets/` were generated for this project with Google Gemini image models (prompts in `tools/gen_assets.py`). PayPal's name and buttons are rendered by PayPal's own SDK; no PayPal logos are bundled.

## Research data

The cartel-pattern model (`backend/quoteguard/research/cartel_model_v1.json`) was trained on the replication data of D. Imhof and H. Wallimann, *Detecting bid-rigging coalitions in different countries and auction formats* (International Review of Law and Economics, 2021), Mendeley Data, doi:10.17632/x8jwmbcpgn.1, licensed **CC BY 4.0** (https://creativecommons.org/licenses/by/4.0/). Changes: screens converted to within-market percentiles; a model was fitted on them. The data itself is not redistributed here (`research/bid_rigging/get_data.sh` downloads it). Okinawa and Italian data originate from Ishii (2014) and Conley & Decarolis (2016) as cited by the data authors.
