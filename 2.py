import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Access individual environment variables
upload_dir = os.getenv("UPLOAD_DIR")
#print(f"UPLOAD_DIR: {upload_dir}") # print sensitive data to the console is risky

# Print all environment variables (less secure, but useful for debugging)
#for key, value in os.environ.items():
#    print(f"{key}: {value}")

#Accessing them one by one is a safe approach
print(f"UPLOAD_DIR is set" if upload_dir else "UPLOAD_DIR is not set")