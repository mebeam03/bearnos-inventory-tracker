"""SQLite-backed inventory core for the Bearno's Inventory Tracker.

Quantities are stored in the *small counting unit* for each ingredient
(e.g. bags, cans, bottles). A box or bucket is an editable multiple of it.
No POS data, sales assumptions, or forecast calculations are used.
"""
from __future__ import annotations

import csv
from contextlib import contextmanager
import math
import sqlite3
import uuid
from datetime import date, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  category TEXT NOT NULL,
  unit_label TEXT NOT NULL,
  package_label TEXT NOT NULL DEFAULT '',
  units_per_package REAL NOT NULL DEFAULT 0,
  min_units REAL NOT NULL DEFAULT 0,
  on_hand REAL NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  allow_partial INTEGER NOT NULL DEFAULT 1,
  notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS movements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('COUNT', 'DELIVERY')),
  item_id INTEGER NOT NULL REFERENCES items(id),
  previous_units REAL NOT NULL,
  new_units REAL NOT NULL,
  change_units REAL NOT NULL,
  supplier TEXT,
  event_date TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_movements_time ON movements(recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_movements_batch ON movements(batch_id);
CREATE TABLE IF NOT EXISTS app_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


@contextmanager
def connect(path: str | Path):
    """Connect and always close SQLite properly after each transaction."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        with conn:
            yield conn
    finally:
        conn.close()


def init_database(path: str | Path, catalog_csv: str | Path):
    """Initialize the starter catalog or migrate a previous local database.

    Historical counts and deliveries remain unchanged. More realistic sample
    balances are assigned only to items without any recorded movements.
    """
    with Path(catalog_csv).open(newline='', encoding='utf-8-sig') as handle:
        catalog = list(csv.DictReader(handle))

    with connect(path) as conn:
        conn.executescript(SCHEMA)
        existing = conn.execute('SELECT COUNT(*) FROM items').fetchone()[0]
        upgraded = conn.execute(
            "SELECT value FROM app_meta WHERE key='menu_catalog_v3'"
        ).fetchone()
        if existing and upgraded:
            _upgrade_packaging_v4(conn, catalog)
            return

        from menu_categories import PREVIOUS_CATEGORIES
        for entry in catalog:
            current = conn.execute(
                'SELECT * FROM items WHERE name=?', (entry['name'],)
            ).fetchone()
            if current is None:
                conn.execute('''INSERT INTO items
                    (name, category, unit_label, package_label, units_per_package,
                     min_units, on_hand, active, allow_partial, notes)
                    VALUES (?,?,?,?,?,?,?,?,?,?)''', (
                        entry['name'], entry['category'], entry['unit_label'],
                        entry['package_label'], float(entry['units_per_package']),
                        float(entry['min_units']), float(entry['starting_units']),
                        int(entry['active']), int(entry['allow_partial']), entry['notes'],
                    ))
                continue

            # Reclassify only previously recognized category names, not any
            # custom categories the user created.
            if current['category'] in PREVIOUS_CATEGORIES:
                conn.execute(
                    'UPDATE items SET category=? WHERE id=?',
                    (entry['category'], current['id']),
                )

            if not upgraded:
                touched = conn.execute(
                    'SELECT 1 FROM movements WHERE item_id=? LIMIT 1',
                    (current['id'],),
                ).fetchone()
                if not touched:
                    conn.execute('''UPDATE items
                        SET on_hand=?, min_units=?, active=? WHERE id=?''', (
                            float(entry['starting_units']), float(entry['min_units']),
                            int(entry['active']), current['id'],
                        ))
                elif float(current['min_units']) == 0:
                    conn.execute(
                        'UPDATE items SET min_units=? WHERE id=?',
                        (float(entry['min_units']), current['id']),
                    )

        # The old catalog included an unused Honey Dijon placeholder. The
        # printed menu lists Honey Mustard; keep old history but hide duplicate.
        conn.execute("UPDATE items SET active=0 WHERE name='Honey Dijon'")
        conn.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES ('menu_catalog_v3','1')")
        _upgrade_packaging_v4(conn, catalog)


def _upgrade_packaging_v4(conn, catalog):
    # Fill missing sample packages once; never overwrite saved physical counts.
    if conn.execute("SELECT 1 FROM app_meta WHERE key='menu_catalog_v4'").fetchone():
        return
    # These are v3's original demonstration stocks, before the amber examples.
    previous_examples = {
        'Italian sausage':12, 'French fries':9, 'Coke 2L':72,
        'Spaghetti':8, 'BBQ sauce':8, 'Blue cheese dressing':5, 'Penne':7,
    }
    for entry in catalog:
        row = conn.execute('SELECT * FROM items WHERE name=?', (entry['name'],)).fetchone()
        if row is None:
            continue
        if not row['package_label'] or float(row['units_per_package']) <= 0:
            conn.execute('''UPDATE items SET package_label=?, units_per_package=?
                            WHERE id=?''',
                         (entry['package_label'], float(entry['units_per_package']),row['id']))
        old = previous_examples.get(entry['name'])
        if old is not None and abs(float(row['on_hand']) - old) < 1e-8:
            had_record = conn.execute('SELECT 1 FROM movements WHERE item_id=? LIMIT 1',
                                      (row['id'],)).fetchone()
            if not had_record:
                conn.execute('UPDATE items SET on_hand=? WHERE id=?',
                             (float(entry['starting_units']),row['id']))
    conn.execute("INSERT OR REPLACE INTO app_meta(key,value) VALUES ('menu_catalog_v4','1')")

def list_items(path, *, active_only=True):
    with connect(path) as conn:
        q = 'SELECT * FROM items'
        if active_only:
            q += ' WHERE active=1'
        q += ' ORDER BY category, name'
        return [dict(x) for x in conn.execute(q)]


def get_item(path, item_id):
    with connect(path) as conn:
        row = conn.execute('SELECT * FROM items WHERE id=?', (item_id,)).fetchone()
        if row is None:
            raise ValueError(f'Unknown inventory item: {item_id}')
        return dict(row)


def nonnegative(value, label='Quantity'):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label} must be a number') from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f'{label} cannot be negative or infinite')
    return number


def count_to_units(item, packages=0, units=0, fraction=0):
    packages = nonnegative(packages, 'Packages')
    units = nonnegative(units, 'Units')
    fraction = nonnegative(fraction, 'Open fraction')
    if packages != int(packages) or units != int(units):
        raise ValueError('Full containers must be whole numbers')
    if fraction not in {0, .25, .5, .75}:
        raise ValueError('Partial containers must be 0, 1/4, 1/2, or 3/4')
    if fraction and not item['allow_partial']:
        raise ValueError('Partial counts are disabled for this item')
    multiplier = nonnegative(item['units_per_package'], 'Package size')
    if packages and multiplier <= 0:
        raise ValueError('Package quantity must be configured before counting packages')
    return round(packages * multiplier + units + fraction, 4)


def split_units(item, quantity):
    value = nonnegative(quantity)
    mult = float(item['units_per_package'])
    if mult > 0:
        packages = int((value + 1e-8) // mult)
        remainder = round(value - packages * mult, 4)
    else:
        packages = 0
        remainder = value
    units = int(remainder + 1e-8)
    fraction = round(remainder - units, 4)
    # Preserve rare non-quarter values rather than silently rounding historical data.
    if abs(fraction) < 1e-8:
        fraction = 0
    return packages, units, fraction


def format_quantity(item, quantity):
    packages, units, fraction = split_units(item, quantity)
    out = []
    if packages:
        out.append(f"{packages:g} {plural(item['package_label'],packages)}")
    if units:
        out.append(f"{units:g} {plural(item['unit_label'],units)}")
    if fraction:
        part = {0.25:'¼',0.5:'½',0.75:'¾'}.get(fraction, f'{fraction:g}')
        out.append(f"{part} {item['unit_label']}")
    return ' + '.join(out) if out else f"0 {plural(item['unit_label'],0)}"


def plural(label, amount):
    label = label or 'unit'
    if amount == 1:
        return label
    return label + ('es' if label.endswith(('ch','sh','x','s')) else 's')


def status(item):
    """Simple color bands: red below minimum, amber at 100–150%, green above."""
    available = float(item['on_hand'])
    minimum = float(item['min_units'])
    if available <= 0:
        return 'Out'
    if minimum <= 0:
        return 'Not set'
    if available < minimum:
        return 'Low'
    if available <= 1.5 * minimum:
        return 'Near'
    return 'OK'


def _submit(path, kind, entries, *, supplier=None, event_date=None, note=''):
    if kind not in ('COUNT','DELIVERY'):
        raise ValueError('Invalid transaction type')
    if not entries:
        raise ValueError('Select at least one ingredient')
    if supplier is not None and supplier not in ('Webstaurant', 'GFS'):
        raise ValueError('Unsupported supplier')
    event_date = (event_date or date.today()).isoformat() if isinstance(event_date or date.today(), date) else str(event_date)
    date.fromisoformat(event_date)
    batch = uuid.uuid4().hex
    now = datetime.now().isoformat(timespec='seconds')
    with connect(path) as conn:
        seen = set()
        for item_id, amount in entries:
            item_id = int(item_id)
            if item_id in seen:
                raise ValueError('An ingredient was submitted more than once')
            seen.add(item_id)
            qty = nonnegative(amount)
            row = conn.execute('SELECT * FROM items WHERE id=? AND active=1', (item_id,)).fetchone()
            if row is None:
                raise ValueError('Ingredient no longer available')
            before = float(row['on_hand'])
            after = qty if kind == 'COUNT' else before + qty
            after = round(after, 4)
            conn.execute('UPDATE items SET on_hand=? WHERE id=?',(after,item_id))
            conn.execute('''INSERT INTO movements
                (batch_id,kind,item_id,previous_units,new_units,change_units,
                 supplier,event_date,recorded_at,note)
                 VALUES(?,?,?,?,?,?,?,?,?,?)''',
                 (batch,kind,item_id,before,after,round(after-before,4),supplier,
                  event_date,now,note[:240]))
    return batch


def save_count(path, entries, note=''):
    """Replace the last recorded balances with physical quantities.
    A difference is a reconciliation difference, NOT necessarily waste.
    """
    return _submit(path,'COUNT',entries,note=note)


def receive_delivery(path, entries, supplier='Webstaurant', delivery_date=None, note=''):
    return _submit(path,'DELIVERY',entries,supplier=supplier,event_date=delivery_date,note=note)


def history(path, limit=300):
    with connect(path) as conn:
        q = '''SELECT m.*, i.name, i.unit_label, i.package_label,
                 i.units_per_package, i.allow_partial
                 FROM movements m JOIN items i ON i.id=m.item_id
                 ORDER BY m.id DESC LIMIT ?'''
        return [dict(row) for row in conn.execute(q, (int(limit),))]


def add_item(path, *, name, category, unit_label, package_label='',
             units_per_package=0, min_units=0, allow_partial=True, notes=''):
    name = (name or '').strip()
    if not name or not category.strip() or not unit_label.strip():
        raise ValueError('Name, category, and counting unit are required')
    units_per_package=nonnegative(units_per_package,'Package size')
    min_units=nonnegative(min_units,'Minimum stock')
    if bool(package_label.strip()) != (units_per_package > 0):
        raise ValueError('A package name requires its quantity, and vice versa')
    with connect(path) as conn:
        conn.execute('''INSERT INTO items
          (name,category,unit_label,package_label,units_per_package,min_units,allow_partial,notes)
          VALUES(?,?,?,?,?,?,?,?)''',(name,category,unit_label,package_label,
                 units_per_package,min_units,int(allow_partial),notes[:240]))


def update_item(path, item_id, *, category, unit_label, package_label,
                units_per_package, min_units, allow_partial, active, notes):
    if not category.strip() or not unit_label.strip():
        raise ValueError('Category and counting unit are required')
    size=nonnegative(units_per_package,'Package size')
    min_units=nonnegative(min_units,'Minimum stock')
    if bool(package_label.strip()) != (size > 0):
        raise ValueError('A package name requires its quantity, and vice versa')
    with connect(path) as conn:
        conn.execute('''UPDATE items SET category=?,unit_label=?,package_label=?,
             units_per_package=?,min_units=?,allow_partial=?,active=?,notes=?
             WHERE id=?''',(category.strip(),unit_label.strip(),package_label.strip(),
             size,min_units,int(allow_partial),int(active),notes[:240],int(item_id)))
