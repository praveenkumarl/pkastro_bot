import json

# 1. Define your file names
INPUT_FILE = 'numerology_1_108.json'   # Change this to your actual input file name
OUTPUT_FILE = 'numerology_upgraded.json' # The new file that will be created

# 2. Define the Elite "S-Tier" Royal Stars
# Based on the methodology, these are the absolute best numbers
S_TIER_NUMBERS = [19, 23, 33, 45, 46, 108]

# 3. Define the "A-Tier" Highly Magnetic/Powerful Numbers
# (Venus powerhouses, Mercury communicators, and Strategic victors)
A_TIER_NUMBERS = [
    15, 24, 42, 60, 69, # Venus
    14, 32, 41, 50, 59, # Mercury
    27, 37, 51, 55, 91  # Strategic
]

def upgrade_json_data():
    # Load the original JSON data
    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as file:
            data = json.load(file)
    except FileNotFoundError:
        print(f"Error: Could not find {INPUT_FILE}. Please check the filename.")
        return

    # Loop through each number entry and upgrade it
    for entry in data:
        num = entry.get("number")
        is_auspicious = entry.get("is_auspicious", False)
        
        # Determine the Power Tier and Royal Star status
        if num in S_TIER_NUMBERS:
            entry["power_tier"] = "S"
            entry["is_royal_star"] = True
            
            # Inject RAG keywords for Elite numbers
            if "ELITE_NUMBER" not in entry["rag_keywords"]:
                entry["rag_keywords"].extend(["ELITE_NUMBER", "TOP_RECOMMENDATION", "ROYAL_STAR"])
                
        elif num in A_TIER_NUMBERS:
            entry["power_tier"] = "A"
            entry["is_royal_star"] = False
            
            if "HIGHLY_MAGNETIC" not in entry["rag_keywords"]:
                entry["rag_keywords"].append("HIGHLY_MAGNETIC")
                
        elif is_auspicious:
            # If it's auspicious but not S or A tier, it's a solid B tier
            entry["power_tier"] = "B"
            entry["is_royal_star"] = False
            
        else:
            # If it is NOT auspicious, flag it as a warning
            entry["power_tier"] = "WARNING"
            entry["is_royal_star"] = False
            
            # Inject RAG keywords for Destructive numbers
            if "DESTRUCTIVE_NUMBER" not in entry["rag_keywords"]:
                entry["rag_keywords"].extend(["DESTRUCTIVE_NUMBER", "AVOID", "DANGER"])

    # Save the upgraded data to a new JSON file
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    print(f"Successfully upgraded {len(data)} numbers!")
    print(f"Saved to {OUTPUT_FILE}")

# Run the function
if __name__ == "__main__":
    upgrade_json_data()