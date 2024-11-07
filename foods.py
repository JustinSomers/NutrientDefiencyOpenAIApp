from openai import OpenAI
import requests
import json

# Load API keys from config.json
with open('config.json') as config_file:
    config = json.load(config_file)
    client = OpenAI(
    # This is the default and can be omitted
    api_key=config["openai_api_key"]
)
    usda_api_key = config["usda_api_key"]

# The rest of your code remains the same
def get_foods_high_in_nutrient(nutrient_name):
    url = f"https://api.nal.usda.gov/fdc/v1/foods/search?query={nutrient_name}&api_key={usda_api_key}&dataType=Survey%20(FNDDS)"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if 'foods' in data:
            top_foods = [
                food['description'] for food in data['foods'][:10]
                if "formula" not in food['description'].lower() and 
                   "powder" not in food['description'].lower() and
                   "supplement" not in food['description'].lower()
            ]
            return top_foods
    return []

def get_recipe_recommendation(nutrient, foods):
    foods_list = ', '.join(foods)
    prompt = (
        f"I am deficient in {nutrient}. Suggest recipes that are rich in {nutrient} and include ingredients "
        f"such as {foods_list}. Provide the percentage of the daily recommended intake of {nutrient} in each recipe. "
        f"Please format it with a list to show ingredients too in the format of [name] (new line) Ingredients: (ordered list)"
    )
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",  # You can use "gpt-3.5-turbo" as well
        messages=[
            {"role": "user", "content": prompt}
        ],
        max_tokens=500
    )
    
    return response.choices[0].message.content.strip()
# Function to generate recipe details for cooking
def get_recipe_details(recipe_name):
    prompt = (f"Provide a summary of ingredients, cooking instructions, and how to check if {recipe_name} is done. "
              f"Include recommended internal temperatures if applicable, as in an actual internal temperature (for instance, specifying 165 degrees for an example)")
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",  # You can use "gpt-3.5-turbo" as well
        messages=[
            {"role": "user", "content": prompt}
        ],
        max_tokens=500
    )
    return response.choices[0].message.content

# Main function to run the program
def main():
    nutrient = input("Enter the nutrient you're deficient in (e.g., Iron, Calcium, Vitamin C): ")

    print("\nFinding foods rich in that nutrient...")
    foods = get_foods_high_in_nutrient(nutrient)
    if foods:
        print(f"Foods rich in {nutrient}: {', '.join(foods)}")
    else:
        print(f"No specific foods found for {nutrient}. Please try a different nutrient or check the USDA database.")
        return

    print("\nFetching recipe recommendations...")
    recipe_recommendations = get_recipe_recommendation(nutrient, foods)
    print("Recipe Recommendations:\n", recipe_recommendations)

    selected_recipe = input("\nEnter the name of the recipe you want to use: ")
    
    print("\nFetching recipe details...")
    recipe_details = get_recipe_details(selected_recipe)
    print("Recipe Details:\n", recipe_details)

if __name__ == "__main__":
    main()
