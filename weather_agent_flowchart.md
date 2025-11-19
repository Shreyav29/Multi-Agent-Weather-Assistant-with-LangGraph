# Weather Agent Architecture - Mermaid Flowchart

## Overall Flow Diagram

```mermaid
flowchart TD
    Start([User Input]) --> Router[Router Node<br/>LLM Classification]
    
    Router -->|is_weather = True| WeatherAPI[Call Weather API Node<br/>Geocoding + Weather Fetch]
    Router -->|is_weather = False| FinalAnswer[Final Answer Node]
    
    WeatherAPI --> Geocode[Geocode Location<br/>Get Lat/Lon]
    Geocode --> GetWeather[Get Current Weather<br/>Open-Meteo API]
    GetWeather --> Summarizer[Summarizer Node<br/>LLM Natural Language]
    
    Summarizer --> FinalAnswer
    FinalAnswer --> End([Return Answer to User])
    
    style Router fill:#e1f5ff
    style WeatherAPI fill:#fff3e0
    style Summarizer fill:#e1f5ff
    style FinalAnswer fill:#f1f8e9
```

## Detailed Component Architecture

```mermaid
graph TB
    subgraph "State Management"
        State[WeatherState TypedDict<br/>- user_input: str<br/>- is_weather: bool<br/>- location: str<br/>- weather_info: str<br/>- answer: str]
    end
    
    subgraph "Node 1: Router"
        R1[Receive user_input]
        R2[Construct LLM Prompt<br/>Classification Task]
        R3[Gemini API Call<br/>gemini-2.0-flash<br/>temperature=0]
        R4[Parse JSON Response<br/>Extract is_weather & location]
        R5[Backup Heuristic<br/>Regex Extract Location]
        R6[Update State<br/>is_weather, location]
        
        R1 --> R2 --> R3 --> R4 --> R5 --> R6
    end
    
    subgraph "Node 2: Call Weather API"
        W1[Get location from state]
        W2[Geocode Location<br/>Open-Meteo Geocoding API]
        W3{Lat/Lon Found?}
        W4[Get Current Weather<br/>Open-Meteo Weather API]
        W5{Weather Data<br/>Retrieved?}
        W6[Map Weather Code<br/>to Description]
        W7[Format Summary<br/>Temperature, Wind, Condition]
        W8[Update state.weather_info]
        W9[Error: Location Not Found]
        W10[Error: Weather Data Unavailable]
        
        W1 --> W2 --> W3
        W3 -->|Yes| W4
        W3 -->|No| W9
        W4 --> W5
        W5 -->|Yes| W6
        W5 -->|No| W10
        W6 --> W7 --> W8
        W9 --> W8
        W10 --> W8
    end
    
    subgraph "Node 3: Summarizer"
        S1[Check if weather_info exists]
        S2{Weather Info<br/>Available?}
        S3[Construct Summarization Prompt]
        S4[Gemini API Call<br/>gemini-2.0-flash<br/>temperature=0.3<br/>max_tokens=80]
        S5[Extract Natural Language Summary]
        S6[Update state.answer]
        S7[Skip - No Data to Summarize]
        
        S1 --> S2
        S2 -->|Yes| S3 --> S4 --> S5 --> S6
        S2 -->|No| S7
    end
    
    subgraph "Node 4: Final Answer"
        F1{Answer Already Set?}
        F2[Keep Existing Answer]
        F3{Weather Info<br/>Available?}
        F4[Use Weather Info as Answer]
        F5[Default Error Message]
        F6[Return Final State]
        
        F1 -->|Yes| F2 --> F6
        F1 -->|No| F3
        F3 -->|Yes| F4 --> F6
        F3 -->|No| F5 --> F6
    end
    
    State -.-> R1
    R6 -.-> State
    W8 -.-> State
    S6 -.-> State
    F6 -.-> State
```

## Graph Construction Flow

```mermaid
flowchart LR
    subgraph "Build Weather App"
        B1[Create StateGraph<br/>with WeatherState]
        B2[Add Nodes<br/>router, call_weather_api,<br/>summarizer, final_answer]
        B3[Set Entry Point<br/>router]
        B4[Define Conditional Routing<br/>route_from_router function]
        B5[Add Conditional Edge<br/>from router]
        B6[Add Regular Edges<br/>call_weather_api → summarizer<br/>summarizer → final_answer]
        B7[Add End Edge<br/>final_answer → END]
        B8[Compile Graph]
        B9[Return weather_app]
        
        B1 --> B2 --> B3 --> B4 --> B5 --> B6 --> B7 --> B8 --> B9
    end
```

## API Integrations

```mermaid
graph LR
    subgraph "External APIs"
        A1[Google Gemini API<br/>gemini-2.0-flash]
        A2[Open-Meteo Geocoding API<br/>geocoding-api.open-meteo.com]
        A3[Open-Meteo Weather API<br/>api.open-meteo.com]
    end
    
    subgraph "Agent Nodes"
        N1[Router Node]
        N2[Weather API Node]
        N3[Summarizer Node]
    end
    
    N1 -->|Classification Request| A1
    A1 -->|JSON Response| N1
    
    N2 -->|Location Name| A2
    A2 -->|Lat/Lon| N2
    N2 -->|Coordinates| A3
    A3 -->|Weather Data| N2
    
    N3 -->|Raw Weather Info| A1
    A1 -->|Natural Summary| N3
```

## Execution Flow Example

```mermaid
sequenceDiagram
    participant User
    participant App as Weather App
    participant Router as Router Node
    participant Gemini as Gemini API
    participant Weather as Weather API Node
    participant GeoAPI as Geocoding API
    participant MeteoAPI as Weather API
    participant Summarizer as Summarizer Node
    participant Final as Final Answer Node
    
    User->>App: "What's the weather in Seattle?"
    App->>Router: Process Input
    Router->>Gemini: Classify Query
    Gemini-->>Router: {is_weather: true, location: "Seattle"}
    Router->>Weather: Route to Weather API
    Weather->>GeoAPI: Geocode "Seattle"
    GeoAPI-->>Weather: lat=47.6, lon=-122.3
    Weather->>MeteoAPI: Get Current Weather
    MeteoAPI-->>Weather: {temp: 15°C, wind: 12km/h, code: 61}
    Weather->>Summarizer: weather_info set
    Summarizer->>Gemini: Summarize Weather Data
    Gemini-->>Summarizer: "It's currently 15°C with slight rain..."
    Summarizer->>Final: answer set
    Final->>App: Return Final State
    App-->>User: Display Answer
```

## Key Features

### 1. State Management
- **TypedDict Schema**: Strongly typed state shared across all nodes
- **Partial State Updates**: Each node modifies only relevant fields
- **Total=False**: Optional fields for flexible state evolution

### 2. LLM Integration (Gemini)
- **Router Classification**: JSON-structured output for reliable parsing
- **Temperature Control**: 0 for classification, 0.3 for summarization
- **Fallback Handling**: Regex-based backup when JSON parsing fails

### 3. External API Integration
- **Geocoding**: Convert location names to coordinates
- **Weather Data**: Real-time weather from Open-Meteo
- **Error Handling**: Graceful degradation on API failures

### 4. Graph Architecture (LangGraph)
- **Conditional Routing**: Decision-based flow control
- **Linear Pipelines**: Sequential processing for weather queries
- **State Compilation**: Immutable compiled graph for execution

### 5. Natural Language Generation
- **Structured → Natural**: Convert API data to friendly text
- **LLM-Powered**: Context-aware summarization
- **Concise Output**: Token-limited responses

## Configuration

| Component | Model/Service | Key Parameters |
|-----------|---------------|----------------|
| Router Node | gemini-2.0-flash | temp=0, max_tokens=100 |
| Summarizer Node | gemini-2.0-flash | temp=0.3, max_tokens=80 |
| Geocoding API | Open-Meteo | count=1, timeout=5s |
| Weather API | Open-Meteo | current_weather=True |
| Graph Engine | LangGraph | StateGraph + END |
