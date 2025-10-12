from google_auth_oauthlib.flow import InstalledAppFlow
try:
    # scopes = adjust depending on your API, e.g. Gmail, YouTube, Drive
    #SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]
    SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
    
    print (1)
    flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
    creds = flow.run_local_server(port=0)
    print (2)
except Exception as e:
    print(f"Error during OAuth flow: {e}")
    raise

print("Access Token:", creds.token)
print("Refresh Token:", creds.refresh_token)
