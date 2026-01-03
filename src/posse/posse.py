"""
Just a simple hello world function to get build working
"""
def hello() -> str:
    return "Hello world!"

"""
Main entry point for the module 
"""
def main():
    print(hello())

if __name__ == "__main__":
    main()