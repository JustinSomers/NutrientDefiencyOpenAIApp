from openai import OpenAI
import requests
import json
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

def get_recipe_recommendation(nutrient, foods):
    foods_list = ', '.join(foods)
    prompt = (
        f"I am deficient in {nutrient}. Suggest a variety of recipes rich in {nutrient}, such as baked dishes, soups, salads, or other foods, "
        f"using ingredients like {foods_list}. Only include recipes that contain {nutrient}. "
        f"Prioritize food items, but if relevant, include up to 2 drinks or smoothies that also contain {nutrient}. "
        f"Each recipe should be structured as JSON with fields: 'name', 'ingredients', and 'daily_intake_percentage'. "
        f"Please avoid including the phrase '{nutrient}-rich' or similar nutrient-specific terms in the recipe names."
    )
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=700
    )
    
    # Initialize debug flag and raw response for potential troubleshooting
    debug = False
    raw_response = response.choices[0].message.content.strip()

    # Initialize an empty list to collect parsed recipes
    recipes_json = []

    # Split the response into potential JSON blocks and parse each separately
    for line in raw_response.split("\n\n"):
        try:
            # Attempt to parse each block as an individual JSON object
            parsed_recipe = json.loads(line)
            
            # Check for required keys before adding to the list
            if "name" in parsed_recipe and "ingredients" in parsed_recipe and "daily_intake_percentage" in parsed_recipe:
                recipes_json.append(parsed_recipe)
            else:
                print(f"Skipping incomplete recipe entry: {parsed_recipe}")
                
        except json.JSONDecodeError:
            print(f"Failed to parse JSON for line: {line}")
            debug = True  # Set debug flag to True to show raw response
            continue  # Skip this line if it is not valid JSON

    if not recipes_json:
        print("No valid recipes found in the response.")
        debug = True

    # Show raw response only if there's an error or debug flag is set
    if debug:
        print("Raw AI Response:", raw_response)

    # Separate food recipes and drink recipes
    food_recipes = []
    drink_recipes = []
    
    for recipe in recipes_json:
        recipe_lower = recipe["name"].lower()
        is_drink_or_smoothie = any(drink in recipe_lower for drink in ["smoothie", "drink", "juice"])
        
        # Prioritize food recipes over drinks
        if is_drink_or_smoothie:
            if len(drink_recipes) < 2:  # Limit to 2 drinks or smoothies
                drink_recipes.append(recipe)
        else:
            food_recipes.append(recipe)
    
    # Combine results, prioritizing food recipes and adding drinks if needed
    filtered_recipes = food_recipes[:10]  # Start with up to 10 food recipes
    if len(filtered_recipes) < 10:
        filtered_recipes.extend(drink_recipes[:10 - len(filtered_recipes)])  # Add drinks if more are needed

    return filtered_recipes



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


# Main function to run the program
def main():
    nutrient = input("Enter the nutrient you're deficient in (e.g., Iron, Calcium, Vitamin C): ")
    standardized_nutrient = standardize_nutrient_name(nutrient)

    print("\nFinding foods rich in that nutrient...")
    foods = get_foods_high_in_nutrient(standardized_nutrient)
    if foods:
        formatted_foods = "\n".join(f"- {food}" for food in foods)
        print(f"Foods rich in {nutrient}:\n{formatted_foods}")
    else:
        print(f"No specific foods found for {nutrient}. Please try a different nutrient or check the USDA database.")
        return

    print("\nFetching recipe recommendations...")
    recipes = get_recipe_recommendation(nutrient, foods)

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
