from num2words import num2words

def format_amount_words(amount: float) -> str:
    # Convert to 2 decimal places first to avoid long floating point numbers
    amount = round(amount, 2)
    # Split into whole and decimal parts
    whole = int(amount)
    decimal = int((amount - whole) * 100)
    
    if decimal > 0:
        return f"{num2words(whole, lang='en').title()} Rupees and {num2words(decimal, lang='en').title()} Paise Only"
    return f"{num2words(whole, lang='en').title()} Rupees Only"