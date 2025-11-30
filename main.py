from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import composite_router
import threading
import os
from dotenv import load_dotenv

# Load .env file before anything else
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path=env_path, override=True)

app = FastAPI(
    title="Composite Backend Service",
    description="Composite service that orchestrates and encapsulates atomic microservices",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag", "etag", "Location", "Content-Type", "x-firebase-uid"]
)

app.include_router(composite_router.router)

# Add GraphQL endpoint using Ariadne
try:
    from ariadne import graphql
    from graphql_api.ariadne_schema import schema  # type: ignore
    from fastapi import Request
    from fastapi.responses import JSONResponse, HTMLResponse
    import json
    
    @app.post("/graphql")
    async def graphql_post(request: Request):
        """Handle GraphQL POST requests"""
        try:
            data = await request.json()
        except:
            return JSONResponse(
                content={"error": "Invalid JSON"}, 
                status_code=400
            )
        
        # Get firebase_uid from request headers (set by API Gateway middleware)
        firebase_uid = request.headers.get("x-firebase-uid") or request.headers.get("X-Firebase-Uid")
        if not firebase_uid:
            firebase_uid = getattr(request.state, "firebase_uid", None)
        
        # Pass request in context so resolvers can access headers
        success, result = await graphql(
            schema,
            data,
            debug=True,
            context_value={"request": request, "firebase_uid": firebase_uid}
        )
        
        status_code = 200 if success else 400
        return JSONResponse(content=result, status_code=status_code)
    
    @app.get("/graphql")
    async def graphql_get(request: Request):
        """Serve GraphQL Playground"""
        playground_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>GraphQL Playground</title>
            <link rel="stylesheet" href="https://unpkg.com/graphql-playground-react/build/static/css/index.css" />
            <link rel="shortcut icon" href="https://unpkg.com/graphql-playground-react/build/favicon.png" />
            <script src="https://unpkg.com/graphql-playground-react/build/static/js/middleware.js"></script>
        </head>
        <body>
            <div id="root"></div>
            <script>
                window.addEventListener('load', function (event) {
                    GraphQLPlayground.init(document.getElementById('root'), {
                        endpoint: window.location.origin + '/graphql'
                    })
                })
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=playground_html)
    
    print("✅ GraphQL endpoint enabled at /graphql")
    print("   POST requests to: http://localhost:8004/graphql")
    print("   GET requests to: http://localhost:8004/graphql (GraphQL Playground)")
    print("   Via API Gateway: http://localhost:8000/graphql")
except ImportError as e:
    print("⚠️  GraphQL not available - install ariadne to enable")
    print(f"   Import error: {e}")
    print("   Run: pip install ariadne graphql-core")
except Exception as e:
    print(f"⚠️  Failed to setup GraphQL: {e}")
    import traceback
    traceback.print_exc()
    print("   GraphQL endpoint will not be available, but service will continue")

@app.get("/")
def root():
    return {"status": "Composite Backend Service running", "version": "1.0.0"}

@app.get("/health")
def health():
    return {"status": "healthy", "service": "composite"}


# Start Pub/Sub subscribers in background threads
def start_subscribers():
    """Start Pub/Sub subscribers for email notifications"""
    project_id = os.getenv("GCP_PROJECT_ID", os.getenv("GOOGLE_CLOUD_PROJECT", ""))
    
    if not project_id:
        print("⚠️  GCP_PROJECT_ID not set, Pub/Sub subscribers will not start")
        print("   Set GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT to enable Pub/Sub")
        return
    
    try:
        from pubsub.subscribers import start_event_subscriber, start_user_subscriber
        
        # Start event subscriber in background thread
        event_thread = threading.Thread(
            target=start_event_subscriber,
            daemon=True,
            name="EventSubscriber"
        )
        event_thread.start()
        print("✅ Started event-created subscriber thread")
        
        # Start user subscriber in background thread
        user_thread = threading.Thread(
            target=start_user_subscriber,
            daemon=True,
            name="UserSubscriber"
        )
        user_thread.start()
        print("✅ Started user-created subscriber thread")
        
    except Exception as e:
        print(f"⚠️  Failed to start Pub/Sub subscribers: {e}")
        print("   Email notifications will not be sent, but service will continue")
        import traceback
        traceback.print_exc()


# Start subscribers when app starts
@app.on_event("startup")
async def startup_event():
    """Start Pub/Sub subscribers on application startup"""
    print("🚀 Starting Composite Service with Pub/Sub subscribers...")
    start_subscribers()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)  # Changed port to 8004

