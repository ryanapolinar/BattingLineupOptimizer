# ⚾ MLB Batting Lineup Optimizer
## https://mlb-lineup-optimizer-ryanapolinar.streamlit.app/

A Streamlit web app that compares a team's actual starting batting order against sabermetric-optimized lineups, built around OBP and wRC+.

This project was inspired by the video **[Mario Super Sluggers' Anti-Analytics Lineups](https://youtu.be/SY7hUFzVijw?si=K9XdFYmCo2yHbJfZ&t=526)**.

## What it does

The app pulls a team's latest starting lineup from MLB StatsAPI and generates three optimized batting orders, shown across three tabs:

- **⬜ OBP Optimized** — sorts the lineup by On Base Percentage, putting the best on-base hitters at the top.
- **⚾ WRC+ Optimized** — ranks by wRC+ (Weighted Runs Created Plus), stacking the best run producers in the heart of the order.
- **🚀 Hybrid Optimized** — blends OBP, wRC+, and handedness using the heuristic from the video above.

Each optimized table also shows each player's **Actual Slot** and **Movement** (how far they shifted from the real lineup), and supports CSV download of the results.

## Disclaimer

The stats come from the MLB StatsAPI and are intended as a fun, analytics-driven exercise. Lineup optimization is one way to think about building a batting order. At the end of the day, **baseball is played on the field, not on a computer**. Remember to have fun, and go watch your local baseball game!
