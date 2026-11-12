"""Bearno's Inventory Tracker

Run with: python3 -m streamlit run app.py
Physical counts replace balances; deliveries add to balances.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from inventory_engine import (
    add_item, count_to_units, format_quantity, history, init_database,
    list_items, plural, receive_delivery, save_count, split_units, status,
    update_item,
)
from menu_categories import ordered_categories

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "inventory.db"
CATALOG = ROOT / "data" / "ingredient_catalog.csv"

st.set_page_config(
    page_title="Bearno's Inventory Tracker", page_icon="🍕",
    layout="wide", initial_sidebar_state="expanded",
)
init_database(DB, CATALOG)

# styling from original website
st.markdown("""
<style>
:root {--red:#A5192D; --forest:#075536; --gold:#D7AB3E;
       --ink:#292522; --muted:#756E68; --line:#E8DED6;}
.stApp, [data-testid="stAppViewContainer"] {background:#FCFAF7;}
.block-container {max-width:1250px; padding-top:1.45rem; padding-bottom:2.5rem;}
[data-testid="stSidebar"] {background:#FFFFFF; border-right:1px solid var(--line);}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {gap:.65rem;}
[data-testid="stSidebar"] [role="radiogroup"] {gap:.38rem;}
h1 {color:#292522!important; font-size:2.05rem!important; font-weight:800!important;
    letter-spacing:-.04em!important; margin:0 0 .85rem!important;}
h2,h3 {color:#292522!important;}
.brand {border-top:4px solid var(--forest);padding:1.1rem .15rem 1.2rem;
        margin-bottom:1.05rem;border-bottom:1px solid var(--line);}
.brand-title {font-family:Georgia,serif;font-size:1.48rem;font-weight:800;color:var(--red);}
.brand-location {color:var(--forest);font-size:.8rem;font-weight:700;
                 letter-spacing:.025em;margin-top:.25rem;}
.top-rule {height:4px; width:80px;background:var(--red);border-radius:4px;
           margin:-.25rem 0 1.2rem;}
.section {font-size:1.03rem;font-weight:800;color:var(--forest);margin:.8rem 0 .55rem;}
[data-testid="stForm"] {background:white;border:1px solid var(--line);
                         border-radius:12px;padding:1rem 1.15rem;}
[data-testid="stDataFrame"] {border:1px solid var(--line);border-radius:8px;overflow:hidden;}
[data-testid="stWidgetLabel"] p {color:#554C47!important;}
[data-testid="stCaptionContainer"] p {color:#6D655F!important;}
[data-testid="stButton"] button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primary"] {
  background:var(--red)!important; border-color:var(--red)!important;
  color:#fff!important; border-radius:7px!important; font-weight:750;}
[data-testid="stButton"] button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] button[kind="primary"]:hover {
  background:#821427!important; border-color:#821427!important;}
/* Small, legible counting rows. Keys turn verified rows green immediately. */
[class*="st-key-countrow_"] {background:#FFFFFF!important;
  border:1px solid #E5DAD2!important;border-radius:10px!important;
  padding:.55rem .85rem!important;margin-bottom:.4rem!important;}
[class*="st-key-countrow_"][class*="_done"] {background:#E5F5E9!important;
  border:2px solid #4B9B68!important;}
[class*="st-key-deliveryrow_"] {background:#FFFFFF!important;
  border:1px solid #E5DAD2!important;border-radius:10px!important;
  padding:.5rem .85rem!important;margin-bottom:.4rem!important;}
[class*="st-key-countrow_"] [data-testid="stWidgetLabel"] p,
[class*="st-key-deliveryrow_"] [data-testid="stWidgetLabel"] p {
  font-size:.81rem!important;font-weight:650!important;white-space:normal!important;
  overflow:visible!important;line-height:1.28!important;}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown('''<div class="brand"><div class="brand-title">🍕 Bearno's Pizza</div>
        <div class="brand-location">Okolona · Preston Highway</div></div>''',
        unsafe_allow_html=True)
    page = st.radio(
        "Navigation", ["Overview", "Count Inventory", "Log Delivery", "History", "Catalog"],
        label_visibility="collapsed",
    )

items = list_items(DB)
all_items = list_items(DB, active_only=False)
categories = ordered_categories(item["category"] for item in items)
all_categories = ordered_categories({item["category"] for item in all_items} | {"Beer"})


def title(text: str) -> None:
    st.title(text)
    st.markdown('<div class="top-rule"></div>', unsafe_allow_html=True)


def confirm(message: str) -> None:
    st.session_state["confirmation"] = message
    st.rerun()


def show_confirmation() -> None:
    message = st.session_state.pop("confirmation", None)
    if message:
        st.success(message)


def format_pack(item: dict) -> str:
    if item["units_per_package"] <= 0:
        return "—"
    number = item["units_per_package"]
    size = int(number) if number.is_integer() else number
    return f"1 {item['package_label']} = {size} {plural(item['unit_label'], size)}"


# A row of native Streamlit widgets is more predictable than a wide data_editor:
# the headings sit directly above the inputs and never truncate inside a grid.
PARTS = {"None": 0.0, "¼": .25, "½": .5, "¾": .75}


def quantity_row(item: dict, *, revision: int, counting: bool):
    """Draw one item and return (item ID, full packs, whole units, open unit, counted)."""
    kind = "count" if counting else "delivery"
    prefix = f"{kind}_{revision}_{item['id']}"
    initial = float(item["on_hand"]) if counting else 0.0
    full_packs, whole_units, fraction = split_units(item, initial)
    checked_key = f"{prefix}_checked"
    was_checked = bool(st.session_state.get(checked_key, False)) if counting else False
    row_key = (f"countrow_{item['id']}_{'done' if was_checked else 'pending'}"
               if counting else f"deliveryrow_{item['id']}")

    with st.container(border=True, key=row_key):
        if counting:
            cells = st.columns([2.9, 1.2, 1.3, 1.3, .87], gap="small")
        else:
            cells = st.columns([2.9, 1.25, 1.25, 1.25], gap="small")

        with cells[0]:
            st.markdown(f"**{escape(item['name'])}**")
            if counting:
                st.caption(f"Recorded: {format_quantity(item, item['on_hand'])}")
            st.caption(f"Package: {format_pack(item)}")

        with cells[1]:
            packs = st.number_input(
                f"Full {plural(item['package_label'], 2)}",
                min_value=0, step=1, value=int(full_packs),
                key=f"{prefix}_packs",
            )
        with cells[2]:
            whole = st.number_input(
                f"Whole {plural(item['unit_label'], 2)}",
                min_value=0, step=1, value=int(whole_units),
                key=f"{prefix}_whole",
            )
        if item["allow_partial"]:
            with cells[3]:
                open_part = st.selectbox(
                    f"Open {item['unit_label']}", list(PARTS),
                    index=list(PARTS.values()).index(fraction) if fraction in PARTS.values() else 0,
                    key=f"{prefix}_open",
                )
        else:
            open_part = "None"
            with cells[3]:
                st.caption("Whole units only")
        if counting:
            with cells[4]:
                checked = st.checkbox("Counted", key=checked_key)
        else:
            checked = True
    return (item["id"], packs, whole, PARTS[open_part], checked)


def validated_rows(row_values, lookup: dict, *, counting: bool):
    output = []
    for item_id, packs, whole, open_fraction, checked in row_values:
        if counting and not checked:
            continue
        item = lookup[item_id]
        try:
            amount = count_to_units(item, packs, whole, open_fraction)
        except ValueError as error:
            raise ValueError(f"{item['name']}: {error}") from error
        if counting or amount > 0:
            output.append((item_id, amount))
    return output


if page == "Overview":
    title("Inventory Overview")
    show_confirmation()
    red_count = sum(status(item) in {"Low", "Out"} for item in items)
    amber_count = sum(status(item) == "Near" for item in items)
    green_count = sum(status(item) == "OK" for item in items)
    st.caption(f"{len(items)} ingredients · 🔴 {red_count} low · 🟠 {amber_count} near minimum · 🟢 {green_count} in stock")

    a, b, c = st.columns([1, 1.3, 1])
    with a:
        category = st.selectbox("Menu section", ["All sections"] + categories)
    with b:
        search = st.text_input("Search inventory", placeholder="Ingredient name")
    with c:
        low_only = st.checkbox("Below minimum only", value=False)

    filtered = [item for item in items
                if (category == "All sections" or item["category"] == category)
                and search.casefold().strip() in item["name"].casefold()
                and (not low_only or status(item) in {"Low", "Out"})]
    indicators = {
        "Out": ("🔴 Out of stock", "#FCE6E7", "#9E1B32"),
        "Low": ("🔴 Low", "#FCE6E7", "#9E1B32"),
        "Near": ("🟠 Near minimum", "#FFF1D7", "#90600A"),
        "OK": ("🟢 In stock", "#E4F4E9", "#126D3B"),
        "Not set": ("Not set", "#F3F0ED", "#635E58"),
    }
    rows = []
    for item in sorted(filtered, key=lambda row: (categories.index(row["category"]), row["name"])):
        state = status(item)
        rows.append({
            "Ingredient": item["name"],
            "Menu section": item["category"],
            "Recorded stock": format_quantity(item, item["on_hand"]),
            "Minimum": format_quantity(item, item["min_units"]),
            "Status": indicators[state][0],
        })
    if rows:
        display = pd.DataFrame(rows)
        def highlight_stock(record):
            text = record["Status"]
            if text.startswith("🔴"):
                _, background, foreground = indicators["Low"]
            elif text.startswith("🟠"):
                _, background, foreground = indicators["Near"]
            elif text.startswith("🟢"):
                _, background, foreground = indicators["OK"]
            else:
                _, background, foreground = indicators["Not set"]
            style = f"background-color:{background};color:{foreground};font-weight:700"
            return [style if field in ("Recorded stock", "Status") else "" for field in display.columns]
        st.dataframe(display.style.apply(highlight_stock, axis=1), hide_index=True,
                     use_container_width=True, height=min(625, 75 + 36 * len(rows)))
    else:
        st.info("No matching ingredients.")
    st.caption("Starting quantities and minimums are examples. Counts and deliveries update the saved balances.")

elif page == "Count Inventory":
    title("Count Inventory")
    show_confirmation()
    a, b = st.columns([1, 1.4])
    with a:
        default = categories.index("Pizza Toppings") + 1 if "Pizza Toppings" in categories else 0
        section = st.selectbox("Menu section", ["All sections"] + categories, index=default)
    with b:
        search = st.text_input("Find ingredient", placeholder="Search within the selected section")

    selected = [item for item in items
                if (section == "All sections" or item["category"] == section)
                and search.casefold().strip() in item["name"].casefold()]
    selected.sort(key=lambda item: (categories.index(item["category"]), item["name"]))
    revision = st.session_state.get("count_revision", 0)
    counted_total = sum(bool(st.session_state.get(f"count_{revision}_{item['id']}_checked", False))
                        for item in selected)
    st.caption(f"{counted_total} of {len(selected)} counted · Checked ingredients turn green")

    if selected:
        input_rows = []
        previous = None
        for item in selected:
            if section == "All sections" and item["category"] != previous:
                st.markdown(f'<div class="section">{escape(item["category"])}</div>', unsafe_allow_html=True)
            previous = item["category"]
            input_rows.append(quantity_row(item, revision=revision, counting=True))
        note = st.text_input("Count note (optional)")
        if st.button("Save Inventory Count", type="primary", disabled=not counted_total):
            try:
                lookup = {item["id"]: item for item in selected}
                entries = validated_rows(input_rows, lookup, counting=True)
                if not entries:
                    st.warning("Mark at least one ingredient as counted.")
                else:
                    save_count(DB, entries, note=note)
                    st.session_state["count_revision"] = revision + 1
                    confirm(f"Saved {len(entries)} ingredient count(s).")
            except ValueError as error:
                st.error(str(error))
    else:
        st.info("No matching ingredients.")

elif page == "Log Delivery":
    title("Log Delivery")
    show_confirmation()
    left, right = st.columns(2)
    supplier = left.selectbox("Supplier", ["Webstaurant", "GFS"])
    delivery_day = right.date_input("Delivery date", value=date.today())
    chosen = st.multiselect("Ingredients received", sorted(item["name"] for item in items))
    if chosen:
        selected = sorted((item for item in items if item["name"] in chosen), key=lambda x: x["name"])
        revision = st.session_state.get("delivery_revision", 0)
        with st.form("delivery_form"):
            input_rows = [quantity_row(item, revision=revision, counting=False) for item in selected]
            submitted = st.form_submit_button("Save Delivery", type="primary")
        if submitted:
            try:
                entries = validated_rows(input_rows, {item["id"]:item for item in selected}, counting=False)
                if not entries:
                    st.warning("Enter a received quantity for at least one ingredient.")
                else:
                    receive_delivery(DB, entries, supplier=supplier, delivery_date=delivery_day)
                    st.session_state["delivery_revision"] = revision + 1
                    confirm(f"Saved delivery of {len(entries)} ingredient(s).")
            except ValueError as error:
                st.error(str(error))

elif page == "History":
    title("Inventory History")
    show_confirmation()
    records = history(DB, limit=2000)
    if not records:
        st.info("Saved counts and deliveries will appear here.")
    else:
        record_type = st.selectbox("Record type", ["All", "Counts", "Deliveries"])
        if record_type != "All":
            kind = "COUNT" if record_type == "Counts" else "DELIVERY"
            records = [record for record in records if record["kind"] == kind]
        rows = [{
            "Date": r["event_date"],
            "Type": "Count" if r["kind"] == "COUNT" else "Delivery",
            "Ingredient": r["name"],
            "Supplier": r["supplier"] or "—",
            "Before": format_quantity(r, r["previous_units"]),
            "After": format_quantity(r, r["new_units"]),
            "Change": f'{r["change_units"]:+g} {plural(r["unit_label"], abs(r["change_units"]))}',
            "Note": r["note"],
        } for r in records]
        st.dataframe(rows, hide_index=True, use_container_width=True,
                     height=min(560, 75 + 36 * max(1, len(rows))))
        if rows:
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
            st.download_button("Download History CSV", buffer.getvalue(),
                               file_name="inventory_history.csv", mime="text/csv")
        st.caption("Count differences are inventory adjustments, not automatically waste.")

elif page == "Catalog":
    title("Ingredient Catalog")
    show_confirmation()
    edit_tab, add_tab = st.tabs(["Edit ingredient", "Add ingredient"])
    with edit_tab:
        selection = st.selectbox("Ingredient", sorted(item["name"] for item in all_items))
        item = next(item for item in all_items if item["name"] == selection)
        with st.form("edit_item"):
            category = st.selectbox("Menu section", all_categories,
                                    index=all_categories.index(item["category"]))
            a, b = st.columns(2)
            unit = a.text_input("Counting unit", value=item["unit_label"])
            minimum = b.number_input("Minimum stock (counting units)", min_value=0.,
                                     value=float(item["min_units"]), step=1.)
            a, b = st.columns(2)
            pack = a.text_input("Larger package name", value=item["package_label"],
                                placeholder="box, case, etc. (optional)")
            size = b.number_input("Units per larger package", min_value=0.,
                                  value=float(item["units_per_package"]), step=1.)
            a, b = st.columns(2)
            partial = a.checkbox("Allow quarter units", value=bool(item["allow_partial"]))
            active = b.checkbox("Active", value=bool(item["active"]))
            note = st.text_input("Notes", value=item["notes"])
            submitted = st.form_submit_button("Save Changes", type="primary")
        if submitted:
            try:
                update_item(DB, item["id"], category=category, unit_label=unit,
                            package_label=pack, units_per_package=size, min_units=minimum,
                            allow_partial=partial, active=active, notes=note)
                confirm("Ingredient updated.")
            except ValueError as error:
                st.error(str(error))
    with add_tab:
        with st.form("add_item"):
            name = st.text_input("Ingredient name")
            category = st.selectbox("Menu section", all_categories, key="new_category")
            a, b = st.columns(2)
            unit = a.text_input("Counting unit", value="bag")
            minimum = b.number_input("Minimum stock", min_value=0., value=1., step=1.)
            a, b = st.columns(2)
            pack = a.text_input("Larger package name (optional)")
            size = b.number_input("Units per larger package", min_value=0., value=0., step=1.)
            partial = st.checkbox("Allow quarter units", value=True)
            submitted = st.form_submit_button("Add Ingredient", type="primary")
        if submitted:
            try:
                add_item(DB, name=name, category=category, unit_label=unit,
                         package_label=pack, units_per_package=size,
                         min_units=minimum, allow_partial=partial)
                confirm("Ingredient added.")
            except ValueError as error:
                st.error(str(error))
    st.caption("Sample stock thresholds and package sizes can be changed here.")
