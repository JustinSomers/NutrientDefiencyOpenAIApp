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

def get_foods_high_in_nutrient(nutrient_name):
    url = f"https://api.nal.usda.gov/fdc/v1/foods/search?query={nutrient_name}&api_key={usda_api_key}&dataType=Survey%20(FNDDS)"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if 'foods' in data:
            # Extract the top food items, filtering out irrelevant entries
            top_foods = [
                food['description'] for food in data['foods'][:10]
                if "formula" not in food['description'].lower() and 
                   "powder" not in food['description'].lower() and
                   "supplement" not in food['description'].lower()
            ]
            return top_foods  # Return as a list for flexibility in formatting
    return []  # Return an empty list if no results found



def get_recipe_recommendation(nutrient, foods):
    foods_list = ', '.join(foods)
    prompt = (
        f"I am deficient in {nutrient}. Suggest recipes that are rich in {nutrient} and include ingredients "
        f"such as {foods_list}. Provide the percentage of the daily recommended intake of {nutrient} in each recipe. "
        f"Please list each recipe as a single block, starting with 'Recipe Name:', followed by 'Ingredients:', and ending with 'Daily Intake:'."
    )
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "user", "content": prompt}
        ],
        max_tokens=500
    )
    
    # Each recipe should be split by double newlines or another distinct delimiter
    recipes_text = response.choices[0].message.content.strip()
    recipes = recipes_text.split("\n\n")  # Separate recipes as single text blocks
    
    return recipes



# Function to generate recipe details for cooking
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

    print("\nFinding foods rich in that nutrient...")
    foods = get_foods_high_in_nutrient(nutrient)
    if foods:
        # Format foods list with bullet points
        formatted_foods = "\n".join(f"- {food}" for food in foods)
        print(f"Foods rich in {nutrient}:\n{formatted_foods}")
    else:
        print(f"No specific foods found for {nutrient}. Please try a different nutrient or check the USDA database.")
        return

    print("\nFetching recipe recommendations...")
    recipes = get_recipe_recommendation(nutrient, foods)

    # Display each recipe as a single numbered block
    print("\nRecipe Recommendations:")
    for idx, recipe in enumerate(recipes, start=1):
        print(f"{idx}. {recipe}\n")  # Each recipe block is numbered as a single unit

    # Prompt the user to select a recipe by number or name
    while True:
        selection = input("\nEnter the number of the recipe you want to use, or type the recipe name: ")
        try:
            # Try to interpret input as a number
            selection_index = int(selection) - 1
            if 0 <= selection_index < len(recipes):
                recipe_name = recipes[selection_index].split("\n")[0].replace("Recipe Name: ", "").strip()
                break
            else:
                print("Please enter a valid recipe number.")
        except ValueError:
            # Use fuzzy matching to find the closest recipe by name
            close_matches = difflib.get_close_matches(selection, [r.split("\n")[0].replace("Recipe Name: ", "").strip() for r in recipes], n=1, cutoff=0.5)
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
