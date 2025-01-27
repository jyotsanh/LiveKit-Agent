    

# Make Outbound call using LiveKit, Twilio Outbound Trunk, OpenAI realtime

## LiveKit

- Open a account in `https://cloud.livekit.io/`
- Setup a CLI in device follow this instruction : `https://docs.livekit.io/home/cli/cli-setup/`
  - For Linux : ``curl -sSL https://get.livekit.io/cli | bash ``
  - For Window : ``winget install LiveKit.LiveKitCLI`` and set the enviromental variable.
- Authenticate your LiveKit CLI with your cloud project.
  - ``lk cloud auth``

## Configure the Twilio SIP trunk

- Open a account in `https://www.twilio.com/en-us` , $15 is free for trail account, 1 free SIP trunk can be created.
- Purchase a free phone number
- Give a Geo-Permission access to your phone number 
- Copy the follwoing credential from your twilio console: Account SID, Auth Token, Twilio phone number
- Install a Twilio CLI from  : `https://www.twilio.com/docs/twilio-cli/getting-started/install`
- Now after installing the Twilio CLI check if it's installed or not by typing : `twilio` in terminal or command prompt.

  - Login through CLI using : `twilio login`

    - When you run `twilio login`.it uses your Account SID and Auth Token to generate an API key, stores the key in a configuration file, and associates the key with the profile to authenticate future requests.

        ```bash
        $ twilio login
        You can find your Account SID and Auth Token at https://www.twilio.com/console
        » Your Auth Token will be used once to create an API Key for future CLI access to your Twilio Account or Subaccount, and then forgotten.
        ? The Account SID for your Twilio Account or Subaccount: ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
        ? Your Twilio Auth Token for your Twilio Account or Subaccount: [hidden]
        ? Shorthand identifier for your profile: dev
        ```
  - To set a profile **dev** as "active",Run `twilio profiles:use dev`
- Create a SIP trunk:

  - ```
    twilio api trunking v1 trunks create \
    --friendly-name "My test trunk" \
    --domain-name "my-test-trunk.pstn.twilio.com"
    ```
- Configure your trunk (Outbound):

  - Copy the values for your Account SID and Auth Token from the Twilio console. Create environment variables to run curl commands:

    - for linux:

        ```
        export TWILIO_ACCOUNT_SID="<twilio_account_sid>"
        export TWILIO_AUTH_TOKEN="<twilio_auth_token>"
        ```
    - for windows:

        ```
        set TWILIO_ACCOUNT_SID=<twilio_account_sid>
        set TWILIO_AUTH_TOKEN=<twilio_auth_token>

        ```

    - Create a Credential from Twilio Console:
        - Go to : Elastic SIP Trunking -> Manage -> Credential lists -> Create a new credential with `username` and `password`

    - Get a list of credential lists:
        - for linux:
            ``` curl -G "https://api.twilio.com/2010-04-01/Accounts/$TWILIO_ACCOUNT_SID/SIP/CredentialLists.json" -u "$TWILIO_ACCOUNT_SID:$TWILIO_AUTH_TOKEN" ```
        - for window:
            ``` curl -G "https://api.twilio.com/2010-04-01/Accounts/%TWILIO_ACCOUNT_SID%/SIP/CredentialLists.json" -u "%TWILIO_ACCOUNT_SID%:%TWILIO_AUTH_TOKEN%" ```

        - The output should look like this: 
            ```
            
            {
                "first_page_uri": "/2010-04-01/Accounts/AC1d21056022342c40d2312bd8f5e796916d4b1/SIP/CredentialLists.json?PageSize=50&Page=0", 
                "end": 1, 
                "credential_lists": [
                    
                    {
                        "sid": "CLc7c249b4d87acb4878dfd447dd6647de", 
                        "account_sid": "AC1d21056022342c40d2312bd8f5e796916d4b1",
                        "friendly_name": "myTrunk", 
                        "date_created": "Mon, 20 Jan 2025 09:37:54 +0000", 
                        "date_updated": "Mon, 20 Jan 2025 09:37:54 +0000", 
                        "uri": "/2010-04-01/Accounts/AC1d21056022342c40d2312bd8f5e796916d4b1/SIP/CredentialLists/CLc7c249b4d87acb4878dfd447dd6647de.json", "subresource_uris": {
                        "credentials": "/2010-04-01/Accounts/AC1d21056022342c40d2312bd8f5e796916d4b1/SIP/CredentialLists/CLc7c249b4d87acb4878dfd447dd6647de/Credentials.json"
                                }
                    }
                            ], 
                                
                                "previous_page_uri": null, 
                                "uri": "/2010-04-01/Accounts/AC1d21056022342c40d2312bd8f5e796916d4b1/SIP/CredentialLists.json?PageSize=50&Page=0",
                                "page_size": 50,
                                "start": 0, 
                                "next_page_uri": null, 
                                "page": 0
                        

            }

            ```
            - find the name of trunk you create in above steps:
                - in my case it is `"friendly_name": "myTrunk"` and Copy the SID for the credential list from the output: `CLc7c249b4d87acb4878dfd447dd6647de`

    - run cmd : `twilio api trunking v1 trunks list` which list the trunk in your account.
        - output should look like: 
        ```
        | SID                                | Friendly Name | Domain Name                      |
        |------------------------------------|---------------|----------------------------------|
        | TK8abc5129ea513772394b909dfmc3691c | My test trunk | my-test-trunk.pstn.twilio.com    |

        ```
        - copy the trunk **SID**
    - Associate a SIP trunk to the credentials list:
        ```
            twilio api trunking v1 trunks credential-lists create \
            --credential-list-sid <credential_list_sid> \
            --trunk-sid <trunk_sid>
        ```
        - in my case:
        ```
            twilio api trunking v1 trunks credential-lists create \
            --credential-list-sid CLc7c249b4d87acb4878dfd447dd6647de \
            --trunk-sid TK8abc5129ea513772394b909dfmc3691c
        
        ```
    - Associate a SIP trunk to the phone number:
        - To list phone numbers: `twilio phone-numbers list`
        - To list trunks: `twilio api trunking v1 trunks list`
        - command to associate a SIP trunk to the phone number: 
            ```
            twilio api trunking v1 trunks phone-numbers create \
            --trunk-sid <twilio_trunk_sid> \
            --phone-number-sid <twilio_phone_number_sid>
            ```


## Create a LiveKit Agent:
    - create a `outbound-trunk.json` file with following credentials:
    
        {
        "trunk": {
            "name": "My outbound trunk",
            "address": "<my-trunk>.pstn.twilio.com",
            "numbers": ["+15105550100"],
            "auth_username": "<username>",
            "auth_password": "<password>"
            }
        }
    
    - `username` and `password` are the credential list password which we create in above steps on Twilio Console.

    - Create the outbound trunk using the CLI:
        - `lk sip outbound create outbound-trunk.json` output of the command returns the trunk ID. Copy the <trunk-id>

    - Create an agent
        - `lk app create --template=outbound-caller-python`
        - provide your trunk_ID
        - OpenAI key
        - we can also change the api key and trunk-id so, after creating the agent
    - check in `.env.local` that your api key and trunk id are correclty configure or not.
    - run your agent `python agent.py dev` in development mode
    - now in another terminal type: `lk dispatch create --new-room --agent-name outbound-caller --metadata '+9779828595633'`