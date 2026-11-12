"""Menu-based ingredient groups inspired by the supplied Bearno's printed menu.

A physical ingredient is counted only once, even when it appears in many dishes.
"""

CATEGORY_ORDER = ['Appetizers', 'Salads & Dressings', 'Pasta', 'Pizza Toppings', 'Pizza Dough & Crusts', 'Italian Sandwiches & Sides', 'Desserts', 'Sauces & Dips', 'Kitchen Staples', '2-Liter Sodas', '20-oz Sodas', 'Fountain Drinks', 'Other Beverages', 'Beer']

MENU_GROUPS = {'Appetizers': ['Chicken wings', 'Chicken tenders', 'Pretzel sticks', 'Meatballs'], 'Salads & Dressings': ['Salad mix', 'Cucumbers', 'Croutons', 'Ranch', 'Blue cheese dressing', 'Honey mustard', 'Light Italian (Golden Italian)', 'Creamy Italian', 'Red wine vinaigrette', 'French dressing', 'Fat-free ranch', 'Thousand Island', 'Italian dressing'], 'Pasta': ['Spaghetti', 'Penne', 'Lasagna noodles', 'Ricotta cheese'], 'Pizza Toppings': ['Shredded mozzarella', 'Shredded cheddar', 'Pepperoni', 'Italian sausage', 'Link sausage', 'Ham', 'Bacon bits', 'Salami', 'Hamburger', 'Fajita chicken', 'Anchovies', 'White onion', 'Red onion', 'Green pepper', 'Mushrooms', 'Green olives', 'Black olives', 'Banana peppers', 'Pepperoncini', 'Jalapeños', 'Pineapple', 'Tomatoes'], 'Pizza Dough & Crusts': ['Cauliflower crust', 'Gluten-free crust', 'Flour', 'High-gluten flour', 'Yeast', 'Sugar', 'Salt'], 'Italian Sandwiches & Sides': ['Steak patties', 'Buns', 'Mozzarella slices', 'Cheddar slices', 'Sandwich lettuce', 'Pickle spears', 'French fries', "Lay's potato chips"], 'Desserts': ['Chocolate chip cookies', 'Large brownies', 'Cream cheese icing', 'Cinnamon sugar', 'Derby pie'], 'Sauces & Dips': ['Pizza sauce', 'Marinara sauce', 'BBQ sauce', 'Buffalo sauce', 'Beer cheese', 'Mayonnaise', 'Spicy blue cheese dip'], 'Kitchen Staples': ['Parmesan cheese', 'Margarine', 'Oregano', 'Basil', 'Garlic salt', 'Poppy seeds', 'Sesame seeds', 'Red pepper flakes']}

CATEGORY_BY_NAME = {
    name: category
    for category, names in MENU_GROUPS.items()
    for name in names
}

PREVIOUS_CATEGORIES = (
    'Cheese & Dairy', 'Meats & Proteins', 'Produce & Salads',
    'Sauces & Dressings', 'Seasonings & Baking',
    'Pasta, Sides & Desserts',
    'Appetizers', 'Salads & Dressings', 'Pasta', 'Pizza Toppings',
    'Pizza Dough & Crusts', 'Italian Sandwiches & Sides',
    'Desserts', 'Extras & Kitchen Staples', 'Sauces & Dips', 'Kitchen Staples',
)

def ordered_categories(categories):
    categories = set(categories)
    return [name for name in CATEGORY_ORDER if name in categories] + sorted(categories - set(CATEGORY_ORDER))
