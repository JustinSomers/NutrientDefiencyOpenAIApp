from openai import OpenAI
import requests
import json
import random
import difflib  # For fuzzy matching

# Load API keys from config.json
with open('config.json') as config_file:
    config = json.load(config_file)
    client = OpenAI(api_key=config["openai_api_key"])
    usda_api_key = config["usda_api_key"]
    youtube_api_key = config["youtube_api_key"]

# Mapping of nutrient variants to a standardized nutrient name
NUTRIENT_VARIANTS = {
    "vitamin d3": "vitamin d",
    "vitamin d2": "vitamin d",
    "vitamin d": "vitamin d",
    "vitamin c": "vitamin c",
    "ascorbic acid": "vitamin c",
    "iron": "iron",
    "heme iron": "iron",
    "non-heme iron": "iron",
    "calcium": "calcium",
    "ca": "calcium",
    # Add more mappings as needed
}

def standardize_nutrient_name(nutrient):
    # Standardize nutrient name based on known variants
    return NUTRIENT_VARIANTS.get(nutrient.lower(), nutrient)


def get_foods_high_in_nutrient(nutrient_name):
    url = f"https://api.nal.usda.gov/fdc/v1/foods/search?query={nutrient_name}&api_key={usda_api_key}&dataType=Survey%20(FNDDS)"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if 'foods' in data:
            excluded_keywords = ["formula", "powder", "supplement", "infant", "baby"]
            allowed_drink_keywords = ["smoothie", "drink"]
            top_foods = []
            seen_foods = set()
            drink_count = 0  # Track the number of drinks or smoothies added
            
            for food in data['foods']:
                description = food['description'].lower()
                
                # Skip entirely excluded items
                if any(exclude in description for exclude in excluded_keywords):
                    continue
                
                # Limit drinks and smoothies to a maximum of 2 entries
                if any(drink in description for drink in allowed_drink_keywords):
                    if drink_count < 2:
                        drink_count += 1
                    else:
                        continue  # Skip if we already have enough drinks
                
                # Add food item if it's unique
                if description not in seen_foods:
                    top_foods.append(food['description'])
                    seen_foods.add(description)
                
                # Stop once we have a good mix of results
                if len(top_foods) >= 10:
                    break
            return top_foods
    return []  # Return an empty list if no results found

    foods_list = ', '.join(foods)
    prompt = (
        f"I am looking for recipes rich in {nutrient}. Please provide recipes that contain {nutrient} "
        f"from diverse sources, with a focus on high-{nutrient} options. Avoid using terms like '{nutrient}-packed' "
        f"in the titles and instead give descriptive recipe names. "
        f"Respond strictly in JSON array format, with each recipe as an object containing 'name', 'ingredients', "
        f"and 'daily_intake_percentage'.\n\n"
        f"The JSON structure should look like this:\n\n"
        f"[\n"
        f"  {{\n"
        f"    \"name\": \"Recipe Name\",\n"
        f"    \"ingredients\": [\"Ingredient1\", \"Ingredient2\"],\n"
        f"    \"daily_intake_percentage\": \"25%\"\n"
        f"  }},\n"
        f"  ...\n"
        f"]\n\n"
        f"Please prioritize options with higher {nutrient} content if possible, and include up to 2 drinks or smoothies."
    )
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=700
    )
    
    raw_response = response.choices[0].message.content.strip()

    # Parse the response as JSON
    try:
        recipes_json = json.loads(raw_response)

        # Verify if it's a JSON array of dictionaries
        if isinstance(recipes_json, list) and all(isinstance(item, dict) for item in recipes_json):
            # Sort recipes by daily intake percentage (highest content first)
            recipes_json.sort(key=lambda x: int(x["daily_intake_percentage"].strip('%')), reverse=True)
            return recipes_json
        else:
            print("Unexpected format: AI response is not a JSON array of recipes.")
            print("Raw AI Response:", raw_response)
            return []
    
    except json.JSONDecodeError:
        print("Failed to parse JSON response. Showing raw AI response for troubleshooting.")
        print("Raw AI Response:", raw_response)
        return []

def get_recipe_details(recipe_name):
    prompt = (f"Provide a summary of ingredients, cooking instructions, and how to check if {recipe_name} is done. "
              f"Include recommended internal temperatures if applicable.")
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "user", "content": prompt}
        ],
        max_tokens=500
    )
    return response.choices[0].message.content

def get_youtube_tutorial(recipe_name):
    # Modify the search query to be more generic
    search_query = f"{recipe_name} recipe"
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": search_query,
        "type": "video",
        "key": youtube_api_key,
        "maxResults": 3  # Request multiple results to increase chances
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if data["items"]:
            # Suggest the first video found
            video_suggestions = []
            for item in data["items"]:
                video_id = item["id"]["videoId"]
                video_title = item["snippet"]["title"]
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                video_suggestions.append(f"{video_title}\nWatch here: {video_url}")
            # Return the top suggestion or multiple if needed
            return "Suggested YouTube Tutorials:\n" + "\n\n".join(video_suggestions)
    return "No specific tutorial found. Try searching YouTube for more options."


def get_recipe_recommendation(nutrient, foods, preference=None):
    # Rotate food descriptions or related terms to encourage variance
    variability_terms = [
        f"rich in {nutrient}",
        f"high in {nutrient} content",
        f"loaded with {nutrient}",
        f"containing {nutrient}"
    ]
    nutrient_description = random.choice(variability_terms)  # Pick a random description for variety
    
    foods_list = ', '.join(foods)
    preference_text = f" that are {preference}" if preference else ""

    prompt = (
        f"I am looking for recipes {nutrient_description}{preference_text}. "
        f"Please provide a variety of recipes with high-{nutrient} content, focusing on diverse sources. "
        f"Exclude titles like '{nutrient}-packed' and instead provide descriptive recipe names. "
        f"Format the response as a JSON array, with each recipe containing 'name', 'ingredients', and 'daily_intake_percentage'. "
        f"The structure should be as follows:\n\n"
        f"[\n"
        f"  {{\n"
        f"    \"name\": \"Recipe Name\",\n"
        f"    \"ingredients\": [\"Ingredient1\", \"Ingredient2\"],\n"
        f"    \"daily_intake_percentage\": \"25%\"\n"
        f"  }},\n"
        f"  ...\n"
        f"]\n\n"
        f"Please provide around 7-10 recipes, prioritize higher {nutrient} content, and include no more than 2 drinks or smoothies if relevant."
    )
    
    # Use a higher temperature to encourage variance in the results
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=700,
        temperature=0.7  # Higher temperature for more varied results
    )
    
    raw_response = response.choices[0].message.content.strip()

    # Parse the response as JSON
    try:
        recipes_json = json.loads(raw_response)

        # Verify if it's a JSON array of dictionaries
        if isinstance(recipes_json, list) and all(isinstance(item, dict) for item in recipes_json):
            # Sort recipes by daily intake percentage (highest content first)
            recipes_json.sort(key=lambda x: int(x["daily_intake_percentage"].strip('%')), reverse=True)
            return recipes_json
        else:
            print("Unexpected format: AI response is not a JSON array of recipes.")
            print("Raw AI Response:", raw_response)
            return []
    
    except json.JSONDecodeError:
        print("Failed to parse JSON response. Showing raw AI response for troubleshooting.")
        print("Raw AI Response:", raw_response)
        return []

# Extend the main function to ask for preferences
def main():
    nutrient = input("Enter the nutrient you're deficient in (e.g., Iron, Calcium, Vitamin C): ")
    standardized_nutrient = standardize_nutrient_name(nutrient)
    
    # Prompt the user for recipe preferences
    preference = input("Any specific dietary preference? (e.g., gluten-free, vegan, pescatarian, meat-based): ").strip().lower()
    preference = preference if preference else None  # Set to None if empty

    print("\nFinding foods rich in that nutrient...")
    foods = get_foods_high_in_nutrient(standardized_nutrient)
    if foods:
        formatted_foods = "\n".join(f"- {food}" for food in foods)
        print(f"Foods rich in {nutrient}:\n{formatted_foods}")
    else:
        print(f"No specific foods found for {nutrient}. Please try a different nutrient or check the USDA database.")
        return

    print("\nFetching recipe recommendations...")
    recipes = get_recipe_recommendation(nutrient, foods, preference)

    if not recipes:
        print("No recipes found with the specified nutrient.")
        return

    print("\nRecipe Recommendations:")
    for idx, recipe in enumerate(recipes, start=1):
        # Display the recipe in a formatted way
        print(f"{idx}. {recipe['name']}")
        print(f"   Ingredients: {', '.join(recipe['ingredients'])}")
        print(f"   Daily Intake Percentage: {recipe['daily_intake_percentage']}\n")

    # Prompt the user to select a recipe by number or name
    while True:
        selection = input("\nEnter the number of the recipe you want to use, or type the recipe name: ")
        try:
            # Try to interpret input as a number
            selection_index = int(selection) - 1
            if 0 <= selection_index < len(recipes):
                recipe_name = recipes[selection_index]["name"]
                break
            else:
                print("Please enter a valid recipe number.")
        except ValueError:
            # Use fuzzy matching to find the closest recipe by name
            close_matches = difflib.get_close_matches(
                selection, [r["name"] for r in recipes], n=1, cutoff=0.5
            )
            if close_matches:
                recipe_name = close_matches[0]
                print(f"Using closest match: {recipe_name}")
                break
            else:
                print("No close match found. Please enter a valid recipe name or number.")

    print("\nFetching recipe details...")
    recipe_details = get_recipe_details(recipe_name)
    print("Recipe Details:\n", recipe_details)
    
    print("\nFetching a YouTube tutorial...")
    youtube_tutorial = get_youtube_tutorial(recipe_name)
    print(youtube_tutorial)

if __name__ == "__main__":
    main()
