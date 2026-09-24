# ⚾ MLB Batting Lineup Optimizer

## https://mlb-lineup-optimizer-ryanapolinar.streamlit.app/

A Streamlit web app that compares a team's actual starting batting order against sabermetric-optimized lineups, built around OBP and wRC+.

This project was inspired by the video **[Mario Super Sluggers' Anti-Analytics Lineups](https://youtu.be/SY7hUFzVijw?si=K9XdFYmCo2yHbJfZ&t=526)**.

## What it does

The app pulls a team's starting lineup from MLB StatsAPI and generates four optimized batting orders, shown across four tabs:

- **Game selector** — the latest starting lineup loads and renders **first**, then the **Select Game** dropdown populates in the background with that season's played games. It defaults to **Latest Starting Lineup** and lets you pick any past game, so you can compare how the order changes game to game, then optimize against it.
- **⬜ OBP Optimized** — sorts the lineup by On Base Percentage, putting the best on-base hitters at the top.
- **⚾ WRC+ Optimized** — ranks by wRC+ (Weighted Runs Created Plus), stacking the best run producers in the heart of the order.
- **🚀 Hybrid Optimized** — blends OBP, wRC+, and handedness using the heuristic from the video above.
- **📕 The Book** — applies the fixed slot template from Tom Tango's _The Book_: the three best hitters in slots #1/#2/#4, 4th- and 5th-best in #3/#5, then #6–#9 in descending quality.

Each optimized table also shows each player's **Actual Slot** and **Movement** (how far they shifted from the real lineup), and supports CSV download of the results. Each table highlights its target metric: **OBP** for the OBP table, **wRC+** for the wRC+ and The Book tables, and in **Hybrid** the OBP for the leadoff spot with **wRC+** for every other slot.

## Disclaimer

The stats come from the MLB StatsAPI and are intended as a fun, analytics-driven exercise. Lineup optimization is one way to think about building a batting order. At the end of the day, **baseball is played on the field, not on a computer**. Remember to have fun, and go watch your local baseball game!
