# ==========================================
# 1. INSTALL DEPENDENCIES (if needed)
# ==========================================
# pip install langgraph langchain-core google-genai

# ==========================================
# 2. IMPORTS
# ==========================================
from typing import TypedDict
from langgraph.graph import StateGraph, END
from google import genai
from google.genai import types
import json
import re
import os
from IPython.display import HTML, Markdown, display
from google import api_core
from google.api_core import retry
import langchain
langchain.debug = False  # or True, but False is fine for now

# ==========================================
# 3. API CLIENT
# ==========================================
GEMINI_API_KEY = 'REPLACE WITH YOUR KEY'
client = genai.Client(api_key=GEMINI_API_KEY)
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = "REPLACE WITH YOUR KEY"  # Get from smith.langchain.com

# ==========================================
# 4. STATE DEFINITION
# ==========================================

class WeatherState(TypedDict, total=False):
    user_input: str          # What the user asked
    is_weather: bool         # Whether Gemini thinks it's a weather question
    location: str            # Extracted city/location
    weather_info: str        # Data returned by our weather function
    answer: str              # Final answer to user

# ==========================================
# 5. ROUTER NODE ---> LLM CALL TO DECIDE IF ITS A WEATHER QUERY
# ==========================================

def router_node(state: WeatherState) -> WeatherState:
    """
    Ask Gemini whether the input is a weather query and extract location.
    """

    user_input = state["user_input"]

    prompt = f"""
                    You are a classifier for a weather assistant. 
                    You help us understand if the user query is regarding weather of a particular location. 
                    You also help extracting the location name from the user query. 
                    Given the user message, respond ONLY in STRICT JSON with:

                    {{
                    "is_weather": true/false,
                    "location": "<city>" OR "unknown"
                    }}

                    Examples:

                    User: "What's the weather in Seattle today?"
                    Output: {{"is_weather": true, "location": "Seattle"}}

                    User: "Do you like pizza?"
                    Output: {{"is_weather": false, "location": "unknown"}}

                    Now process:
                    "{user_input}"
"""

    resp = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=100,temperature=0)
    )

    raw = resp.text.strip()
    print("Raw response:", raw)

    # Clean up the response - remove markdown code blocks if present
    if raw.startswith("```"):
        # Remove ```json or ``` at the start and ``` at the end
        lines = raw.split('\n')
        raw = '\n'.join(lines[1:-1]) if len(lines) > 2 else raw
        raw = raw.strip()
    
    # Try to parse JSON returned by Gemini
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"JSON parsing failed: {e}")
        print(f"Raw text was: {raw}")
        # Fallback if parsing fails
        parsed = {
            "is_weather": "weather" in user_input.lower(),
            "location": "unknown"
        }
    # print('---')
    # print(raw, parsed)
    # print('-----')
    is_weather = bool(parsed.get("is_weather", False))
    location = parsed.get("location", "unknown")

    # 🔁 Backup heuristic: extract "in <location>"
    if location == "unknown":
        match = re.search(r"in\s+([A-Za-z\s]+)", user_input, re.IGNORECASE)
        if match:
            location = match.group(1).strip(" ?.!,")

    # Write results back to shared graph state
    state["is_weather"] = is_weather
    state["location"] = location
    

    return state

# ==========================================
# 6. WEATHER API NODE ---> API CALL TO GET ACCURATE WEATHER INFO
# ==========================================

import requests 

#Returns latitude and longitude for a given location in user_query 
def geocode_location(location: str):
    """
    Use Open-Meteo geocoding API to convert a place name into lat/lon.
    Returns (lat, lon) or (None, None) if not found.

    For Hyderabad - https://geocoding-api.open-meteo.com/v1/search?name=Hyderabad

    There could be multiple Hyderabads, you pick the top one as they are ordered as per population.
    You can change it to have a LLM call and ask clarification questions. 
    """
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": location, "count": 1}

    try:
        r = requests.get(url, params=params, timeout=5)
        data = r.json()

        if "results" in data and len(data["results"]) > 0:
            top = data["results"][0]
            return top["latitude"], top["longitude"]

    except Exception as e:
        print("Geocoding failed:", e)

    return None, None


#Get Current weather for given lat/lon
def get_current_weather(lat: float, lon: float):
    """
    Fetch current weather from Open-Meteo.
    Returns a dict with temperature, windspeed, weathercode.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": True
    }

    try:
        r = requests.get(url, params=params, timeout=5)
        data = r.json()

        if "current_weather" in data:
            print(data)
            return data["current_weather"] #This is a dictionary of weather info
        

    except Exception as e:
        print("Weather API failed:", e)

    return None

WEATHER_CODE_MAP = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    95: "Thunderstorm",
}


def call_weather_node(state: WeatherState) -> WeatherState:
    location = state.get("location", "unknown")

    # 1) Convert name → lat/lon
    lat, lon = geocode_location(location)
    if lat is None or lon is None:
        state["weather_info"] = f"Sorry, I could not find weather data for {location}."
        return state

    # 2) Get current weather
    weather = get_current_weather(lat, lon)
    if not weather:
        state["weather_info"] = f"Unable to retrieve weather for {location}."
        return state

    temp = weather.get("temperature")
    wind = weather.get("windspeed")
    code = weather.get("weathercode")
    condition = WEATHER_CODE_MAP.get(code, "Unknown conditions")

    # 3) Create simple summary (Option B1) - This can also be a GEMINI call to make it more descriptive
    summary = (
        f"It is currently {temp}°C with {condition.lower()} "
        f"in {location}. Wind speed is {wind} km/h."
    )

    state["weather_info"] = summary
    return state



# ==========================================
# 7. SUMMARIZER NODE - LLM CALL TO SUMMARIZE THE WEATHER INFORMATION 
# ==========================================



#Adding a new node to the framework
def summarizer_node(state: WeatherState) -> WeatherState:
    """
    Take structured weather_info and location, and ask Gemini to craft
    a natural, friendly sentence. Writes to state["answer"].
    """
    if "weather_info" not in state:
        # Nothing to summarize, leave it to final_answer_node
        return state

    location = state.get("location", "this location")
    base_info = state["weather_info"]

    prompt = f"""
You are a helpful assistant. I have this raw weather info:

Location: {location}
Details: {base_info}

Please rewrite this as a single friendly sentence suitable for a user.
Keep it short and clear.
"""

    resp = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=80,
            temperature=0.3,
        ),
    )

    summary = resp.text.strip()
    state["answer"] = summary
    return state

# ==========================================
# 7. FINAL ANSWER NODE
# ==========================================


def final_answer_node(state: WeatherState) -> WeatherState:
    # If summarizer already set an answer, keep it
    if "answer" in state:
        return state

    # Otherwise fall back to raw weather_info if present
    if "weather_info" in state:
        state["answer"] = state["weather_info"]
    else:
        state["answer"] = (
            "I can only answer simple weather questions right now. Try asking:\n"
            "'What's the weather in Seattle?'"
        )
    return state




# ==========================================
# 9. BUILD THE GRAPH AND TEST THE AGENT
# ==========================================


from langgraph.graph import StateGraph, END

def build_weather_app():
    """
    Build and return the weather app state graph.
    """
    # 1) Create a graph builder with our state type
    builder = StateGraph(WeatherState)

    # 2) Add nodes
    builder.add_node("router", router_node)
    builder.add_node("call_weather_api", call_weather_node)
    builder.add_node("summarizer", summarizer_node)    
    builder.add_node("final_answer", final_answer_node)

    # 3) Set the entry point (first node to run)
    builder.set_entry_point("router")


    # 4) Define conditional edges out of 'router'
    def route_from_router(state: WeatherState) -> str:
        """
        Decide which node to go to from 'router'.
        Return the name of the next node, or END.
        """
        # 1) Prefer explicit LLM classification if available
        if "is_weather" in state:
            if state["is_weather"]:
                return "call_weather_api_string"
            else:
                return "final_answer_string"

        # 2) Fallback for older WeatherState (no is_weather field)
        user_text = state.get("user_input", "").lower()
        if "weather" in user_text:
            return "call_weather_api_string"
        else:
            return "final_answer_string"

    builder.add_conditional_edges(
                                "router",                 # current node name 
                                route_from_router,        # routing function - it inspects state and returns next node name
                                {  #Mapping dict which maps the string returned by routing function to node names in builder
                                    "call_weather_api_string": "call_weather_api",
                                    "final_answer_string": "final_answer",
                                }
    )

    # 5) From start node - 'call_weather_api', always go to end node - 'final_answer'
    builder.add_edge("call_weather_api", "summarizer")
    builder.add_edge("summarizer", "final_answer")

    # 6) From 'final_answer', end the graph
    builder.add_edge("final_answer", END)

    # 7) Compile the graph into a runnable app
    weather_app = builder.compile()

    return weather_app

def test_weather_app(test_input: str):
    """
    Test the weather app with the given user input.
    """
    app = build_weather_app()

    # Initial state with user input
    initial_state: WeatherState = {"user_input": test_input}

    # Run the app
    final_state = app.invoke(initial_state)

    # Print the final answer
    
    for key, value in final_state.items():
        print(f"{key}: {value}") 
    graph = app.get_graph()
    print(graph.to_json())   # or similar
    



# ==========================================
# 9. TEST THE AGENT
# ==========================================


test_cases = [
    #"What's the weather in Seattle?",
    "What's the weather in Seattle right now",
    "Tell me the weather in Hyderabad.",
    #"How's the weather today?",
]

for i in test_cases: 
    print('--------------------------------')
    test_weather_app(i)
    print('--------------------------------')    
