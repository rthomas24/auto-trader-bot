import os
from firebase_functions import scheduler_fn
from firebase_admin import initialize_app
from coinbase.rest import RESTClient
from datetime import datetime
from dotenv import load_dotenv
import json
from firebase_functions.params import SecretParam
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

load_dotenv()
initialize_app()

COINBASE_API_KEY = SecretParam('COINBASE_API_KEY')
COINBASE_API_SECRET = SecretParam('COINBASE_API_SECRET')
SENDGRID_API_KEY = SecretParam('SENDGRID_API_KEY')

class CoinbaseTrader:
    def __init__(self, api_key, api_secret):
        if not api_key or not api_secret:
            raise ValueError("API credentials are not set")
        self.client = RESTClient(api_key=api_key, api_secret=api_secret)

    def market_buy(self, amount_usd, product_id, asset_name):
        """Place a market buy order for the specified USD amount"""
        try:
            print(f"Attempting to buy ${amount_usd} of {product_id}")
            unique_order_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{asset_name}"
            order = self.client.market_order_buy(
                client_order_id=unique_order_id,
                product_id=product_id,
                quote_size=str(amount_usd)
            )
            order_details = order.to_dict()
            print(f"Success - Order details: {order_details}")
            return order_details
        except Exception as e:
            print(f"ERROR in market_buy: {str(e)}")
            print(f"Error type: {type(e).__name__}")
            return f"Failed to purchase {product_id}: {str(e)}"

    def get_account_balance(self):
        """Get only the USD balance from the account"""
        try:

            accounts = self.client.get_accounts(limit=250)
            accounts_dict = json.loads(json.dumps(accounts.to_dict()))
            
            for account in accounts_dict.get('accounts', []):
                if account.get('currency') == 'USD':
                    return float(account.get('available_balance', {}).get('value', 0))
            
            return 0  # Return 0 if no USD account is found
            
        except Exception as e:
            print(f"Error getting USD balance: {str(e)}")
            return 0

def send_email(subject, html_content):
    """Send an email using SendGrid."""
    message = Mail(
        from_email=os.getenv('FROM_EMAIL_ADDRESS'),
        to_emails=os.getenv('TO_EMAIL_ADDRESS'),
        subject=subject,
        html_content=html_content
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY.value)
        sg.send(message)
    except Exception as e:
        print(f"Error sending email: {str(e)}")


@scheduler_fn.on_schedule(schedule="00 11 * * *", timezone="America/New_York", secrets=[COINBASE_API_KEY, COINBASE_API_SECRET, SENDGRID_API_KEY])
def make_purchases(event: scheduler_fn.ScheduledEvent) -> None:
    """
    Scheduled Cloud Function to make market purchases of crypto's choosen.
    Checks USD balance before making purchases.
    """
    try:
        # Access secrets
        api_key = COINBASE_API_KEY.value
        api_secret = COINBASE_API_SECRET.value
        trader = CoinbaseTrader(api_key, api_secret)
    except ValueError as e:
        print(f"Initialization error: {e}")
        return

    # Define the assets and amounts to purchase
    asset_amounts = {
        'BTC': 100,
        'ETH': 100,
    }

    # Calculate total required USD
    total_required = sum(asset_amounts.values())
    
    purchase_results = []
    available_balance = trader.get_account_balance()
    print(f"Available USD balance: ${available_balance}")
    
    if available_balance < total_required:
        print(f"Insufficient funds. Required: ${total_required}, Available: ${available_balance}")
        return

    # Perform market buy for each asset
    for asset, amount_usd in asset_amounts.items():
        product_id = f"{asset}-USD"
        result = trader.market_buy(amount_usd, product_id, asset)
        if isinstance(result, dict):
            success_flag = result.get('success', False)
            purchase_results.append(f"Bought ${amount_usd} of {asset}. Success: {success_flag}")
        else:
            purchase_results.append(f"Purchase failed for {asset}: {result}")

    email_content = f"""
    <h1 style="color: #333; font-family: Arial, sans-serif;">Crypto Purchase Summary</h1>
    
    <div style="margin: 20px 0; padding: 10px; background-color: #f5f5f5; border-radius: 5px;">
        <h2 style="color: #666; margin-bottom: 5px;">Account Balance</h2>
        <p style="font-size: 18px; color: #2ecc71; margin: 0;">Available: ${available_balance:.2f}</p>
    </div>

    <div style="margin: 20px 0;">
        <h2 style="color: #666;">Purchase Details</h2>
        <ul>
            {''.join(f"<li>{result}</li>" for result in purchase_results)}
        </ul>
    </div>

    <p style="color: #666; font-size: 12px; margin-top: 20px;">
        Transaction completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} EST
    </p>
    """

    # Send email with purchase summary
    send_email("Crypto Purchase Summary", email_content)

    print("All purchases completed successfully")