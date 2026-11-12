"""Tests for the manual inventory calculations and SQLite history."""
import csv
import tempfile
import unittest
from pathlib import Path

from inventory_engine import (
    add_item, connect, count_to_units, format_quantity, get_item, history,
    init_database, list_items, receive_delivery, save_count, status, update_item,
)

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'data' / 'ingredient_catalog.csv'


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.db = Path(self.temporary.name) / 'inventory.db'
        init_database(self.db, CATALOG)
        self.items = {item['name']: item for item in list_items(self.db)}

    def tearDown(self):
        self.temporary.cleanup()

    def test_sample_catalog_has_menu_items(self):
        self.assertGreaterEqual(len(self.items), 90)
        names = ['Shredded mozzarella', 'Anchovies', 'Beer cheese', 'Ranch',
                 'Honey mustard', 'Italian dressing', 'Fat-free ranch',
                 'Salad mix', 'Sandwich lettuce', 'Pickle spears',
                 'French fries', "Lay's potato chips", 'Coke 2L', 'Coke syrup']
        for name in names:
            self.assertIn(name, self.items)
        self.assertNotIn('Honey Dijon', self.items)

    def test_categories_reflect_printed_menu(self):
        self.assertEqual(self.items['Anchovies']['category'], 'Pizza Toppings')
        self.assertEqual(self.items['Beer cheese']['category'], 'Sauces & Dips')
        self.assertEqual(self.items['Chicken wings']['category'], 'Appetizers')
        self.assertEqual(self.items['Pretzel sticks']['category'], 'Appetizers')
        self.assertEqual(self.items['Ranch']['category'], 'Salads & Dressings')
        self.assertEqual(self.items['Sandwich lettuce']['category'], 'Italian Sandwiches & Sides')
        self.assertEqual(self.items['Spaghetti']['category'], 'Pasta')
        self.assertEqual(self.items['High-gluten flour']['category'], 'Pizza Dough & Crusts')

    def test_illustrative_levels_differ_and_minimums_are_set(self):
        self.assertEqual(self.items['Shredded mozzarella']['on_hand'], 18)
        self.assertEqual(self.items['Shredded mozzarella']['min_units'], 12)
        self.assertEqual(self.items['Coke 2L']['on_hand'], 30)
        self.assertEqual(self.items['Salad mix']['min_units'], 6)
        self.assertEqual(status(self.items['Salad mix']), 'Low')
        self.assertTrue(all(item['min_units'] > 0 for item in self.items.values()))
        self.assertGreater(len({item['on_hand'] for item in self.items.values()}), 8)

    def test_all_catalog_items_have_example_package_sizes(self):
        all_items = list_items(self.db, active_only=False)
        self.assertEqual(len(all_items), 98)
        self.assertTrue(all(x['package_label'] and x['units_per_package'] > 0
                            for x in all_items))
        self.assertEqual(self.items['Coke 2L']['package_label'], 'pallet')
        self.assertEqual(self.items['Coke 20oz']['package_label'], 'wrapped pack')
        self.assertEqual(self.items['Shredded mozzarella']['units_per_package'], 4)
        self.assertEqual(self.items['Pizza sauce']['units_per_package'], 2)

    def test_red_amber_green_thresholds(self):
        self.assertEqual(status(self.items['Salad mix']), 'Low')
        self.assertEqual(status(self.items['Coke 2L']), 'Near')
        self.assertEqual(status(self.items['Italian sausage']), 'Near')
        self.assertEqual(status(self.items['Shredded mozzarella']), 'Near')
        self.assertEqual(status(self.items['High-gluten flour']), 'OK')
        item = self.items['Coke 2L']
        save_count(self.db, [(item['id'], 0)])
        self.assertEqual(status(get_item(self.db, item['id'])), 'Out')

    def test_v3_package_upgrade_preserves_counted_item(self):
        mozzarella = self.items['Shredded mozzarella']
        sausage = self.items['Italian sausage']
        save_count(self.db, [(mozzarella['id'], 9.5)])
        with connect(self.db) as connection:
            connection.execute("DELETE FROM app_meta WHERE key='menu_catalog_v4'")
            connection.execute("UPDATE items SET package_label='', units_per_package=0 "
                               "WHERE name IN ('Italian sausage','Coke 2L')")
            connection.execute("UPDATE items SET on_hand=12 WHERE name='Italian sausage'")
            connection.execute("UPDATE items SET on_hand=72 WHERE name='Coke 2L'")
        init_database(self.db, CATALOG)
        self.assertEqual(get_item(self.db, mozzarella['id'])['on_hand'], 9.5)
        self.assertEqual(get_item(self.db, sausage['id'])['on_hand'], 8)
        self.assertEqual(get_item(self.db, sausage['id'])['units_per_package'], 2)
        self.assertEqual(next(x for x in list_items(self.db) if x['name']=='Coke 2L')['on_hand'],30)
        self.assertEqual(len(history(self.db)), 1)

    def test_mozzarella_package_conversion(self):
        item = self.items['Shredded mozzarella']
        self.assertEqual(count_to_units(item, 2, 1, .5), 9.5)
        self.assertEqual(format_quantity(item, 9.5), '2 boxes + 1 bag + ½ bag')

    def test_sauce_bucket_can_conversion(self):
        item = self.items['Pizza sauce']
        self.assertEqual(count_to_units(item, 3, 1, 0), 7)
        self.assertEqual(format_quantity(item, 7), '3 buckets + 1 can')

    def test_count_replaces_balance(self):
        item = self.items['Shredded mozzarella']
        save_count(self.db, [(item['id'], 9.5)], note='Closing count')
        after = get_item(self.db, item['id'])
        self.assertEqual(after['on_hand'], 9.5)
        record = history(self.db)[0]
        self.assertEqual(record['previous_units'], 18)
        self.assertEqual(record['new_units'], 9.5)
        self.assertEqual(record['kind'], 'COUNT')
        self.assertEqual(record['note'], 'Closing count')

    def test_delivery_adds_balance(self):
        item = self.items['Italian sausage']
        receive_delivery(self.db, [(item['id'], 6)], supplier='Webstaurant')
        self.assertEqual(get_item(self.db, item['id'])['on_hand'], 14)
        self.assertEqual(history(self.db)[0]['supplier'], 'Webstaurant')

    def test_out_and_low_status(self):
        item = self.items['Shredded mozzarella']
        save_count(self.db, [(item['id'], 0)])
        self.assertEqual(status(get_item(self.db, item['id'])), 'Out')
        save_count(self.db, [(item['id'], 5)])
        self.assertEqual(status(get_item(self.db, item['id'])), 'Low')

    def test_invalid_quantities_are_rejected(self):
        item = self.items['Shredded mozzarella']
        for values in [(-1, 0, 0), (1, 0, .3), (0, .5, 0)]:
            with self.assertRaises(ValueError):
                count_to_units(item, *values)
        no_fraction = self.items['Coke 2L']
        with self.assertRaises(ValueError):
            count_to_units(no_fraction, 0, 2, .5)
        with self.assertRaises(ValueError):
            save_count(self.db, [(item['id'], -1)])

    def test_custom_item_can_be_added_and_edited(self):
        add_item(self.db, name='Extra dipping sauce', category='Sauces & Dips',
                 unit_label='bottle', package_label='case', units_per_package=6,
                 min_units=3)
        item = next(x for x in list_items(self.db) if x['name'] == 'Extra dipping sauce')
        self.assertEqual(item['units_per_package'], 6)
        update_item(self.db, item['id'], category='Sauces & Dips',
                    unit_label='bottle', package_label='case', units_per_package=12,
                    min_units=6, allow_partial=False, active=True, notes='')
        self.assertEqual(get_item(self.db, item['id'])['units_per_package'], 12)

    def test_upgrade_keeps_saved_counts_and_updates_categories(self):
        anchovies = self.items['Anchovies']
        mozzarella = self.items['Shredded mozzarella']
        save_count(self.db, [(mozzarella['id'], 7.5)], note='Previously saved')
        with connect(self.db) as connection:
            connection.execute("UPDATE items SET category='Meats & Proteins' WHERE id=?", (anchovies['id'],))
            connection.execute("UPDATE items SET category='Cheese & Dairy' WHERE id=?", (mozzarella['id'],))
            connection.execute("DELETE FROM app_meta WHERE key='menu_catalog_v3'")
        init_database(self.db, CATALOG)
        self.assertEqual(get_item(self.db, anchovies['id'])['category'], 'Pizza Toppings')
        self.assertEqual(get_item(self.db, mozzarella['id'])['on_hand'], 7.5)
        self.assertEqual(len(history(self.db)), 1)

    def test_duplicate_entries_roll_back(self):
        item = self.items['Shredded mozzarella']
        with self.assertRaises(ValueError):
            save_count(self.db, [(item['id'], 1), (item['id'], 5)])
        self.assertEqual(get_item(self.db, item['id'])['on_hand'], 18)
        self.assertEqual(history(self.db), [])


if __name__ == '__main__':
    unittest.main()
