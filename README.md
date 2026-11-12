# Bearno's Inventory Tracker

A Python programming portfolio project based on a restaurant inventory scenario at Bearno's Pizza (Okolona / Preston Highway, Louisville). The goal is to make manual counts and delivery records easier to maintain **without** connecting to a point-of-sale system.

## Run on a Mac

1. Unzip the folder into `Desktop/Portfolio Projects`.
2. In Terminal, run:

```bash
cd "$HOME/Desktop/Portfolio Projects/Bearnos_Inventory_Tracker"
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

3. The app opens in your browser (usually `http://localhost:8501`). To stop it, press `Control + C` in Terminal.

## What the program does

| Screen | Function |
|---|---|
| **Overview** | Search by menu section and see **red** below-minimum quantities, **amber** near-minimum quantities, and **green** healthy stock. |
| **Count Inventory** | Choose a menu section or search for an ingredient. Enter full packages, whole individual units, and the amount of any open container. Check **Counted** after physically verifying an item; its row turns green immediately. |
| **Log Delivery** | Select ingredients and record what arrived from Webstaurant or GFS. |
| **History** | View saved changes and export records as a CSV. |
| **Catalog** | Change package sizes, minimums, categories, and whether items are active; add new ingredients. |

A **physical count replaces** the previous balance. A **delivery adds** to the balance. SQLite records the previous and new amount for each transaction. Missing stock after a count is a difference to investigate, **not automatically waste**.

## Ingredient catalog and menu reference

The starter catalog is informed by the four-page printed Bearno's menu provided for this project. Relevant menu sections include **Appetizers, Salads, Pasta, Italian Sandwiches, Specialty Pizzas, Build Your Own Pizza, Desserts, and Beverages**. The application organizes *physical ingredients*, not finished menu items. For example, chicken wings are counted once rather than separately for every wing flavor.

- **Anchovies** are under **Pizza Toppings** (listed as a topping on menu page 3).
- **Beer cheese** is under **Sauces & Dips** even though it is served with pretzel sticks.
- The menu lists **Honey Mustard**, **Light Italian**, **Creamy Italian**, **Italian**, **French**, **Ranch**, **Fat Free Ranch**, **Thousand Island**, **Bleu Cheese**, and **Red Wine Vinaigrette** (page 2). Light Italian also has the store nickname *Golden Italian* in this catalog.
- **Salad mix** and **sandwich lettuce** are kept separate.
- Beverage items include separate 2-liter, 20-ounce, and fountain syrup records; beer brands are not invented.

The printed menu describes what customers can order, **not actual storeroom counts or packaging**. Starter quantities, reorder minimums, and some package assumptions are **illustrative sample data** for this college project. They are not official Bearno's operating records. All **98 catalog entries** have example pack sizes, including pallets for 2-liter sodas and wrapped packs for 20-oz bottles. These are assumptions, not verified supplier quantities. There are **98 catalog entries, 95 active**; unverified items are inactive until enabled. Edit these values in **Catalog**.

## Counting example

For shredded mozzarella, the configured packaging is **4 bags per box**. The three counting fields mean: **Full boxes** (unopened cases), **Whole bags** (individual complete bags), and **Open bag** (only the partly used bag). A count of 2 boxes, 1 whole bag, and half an open bag becomes:

```text
2 boxes × 4 bags + 1 bag + 0.5 bag = 9.5 bags
```

For prepared pizza sauce, one bucket is modeled as two cans. The conversion is editable. For bottled soda, the examples use **48 bottles per pallet (2-liter)** and **24 bottles per wrapped pack (20-oz)**. These numbers are illustrative because the location’s actual packaging sizes have not been verified.

## Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit interface and form validation |
| `inventory_engine.py` | Inventory conversion and SQLite operations |
| `menu_categories.py` | Ingredient categories and the category ordering |
| `data/ingredient_catalog.csv` | Editable sample inventory definitions and starting stock |
| `.streamlit/config.toml` | Light theme and menu-inspired colors |
| `tests/test_inventory.py` | Automated tests |

SQLite creates `data/inventory.db` when the app launches. This file stores your actual changes. **Do not upload it to a public GitHub repository with real operational data.**

## Color indicators

- **Red**: stock is **below** its configured minimum, or out entirely.
- **Amber**: stock is **at or within 50% above** its minimum.
- **Green**: stock is **more than 50% above** its minimum.

The minimum and all packaging sizes can be edited in **Catalog**. These are simple operational signals, not predicted sales or forecasts. In **Count Inventory**, ticking **Counted** immediately turns that ingredient row green; pressing **Save Inventory Count** writes only checked rows to SQLite.

## Keeping saved counts when upgrading

If moving from Version 1, 2, or 3, copy only `data/inventory.db` into this folder **before starting Version 4**. The program preserves saved counts and deliveries, and fills in missing packaging configurations. For a few untouched sample items, it also adjusts illustrative stock to show realistic amber states. If you want a completely clean sample dataset, leave `inventory.db` out and let the app create a new one.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The 15 tests cover category assignments, all ingredient packaging, red/amber/green thresholds, package math, count replacement, delivery addition, history records, item editing, validation, and safe upgrades.

## Scope and limitations

This is a small **single-user local college project**. It does not forecast demand, subtract sales automatically, place purchase orders, or connect to Heartland POS. The shown stock is the **last saved physical count plus logged deliveries**, not necessarily the quantity currently in the kitchen. Public hosting would require user-isolated storage rather than one shared local SQLite file.
