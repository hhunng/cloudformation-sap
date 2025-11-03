import json

def lambda_handler(event, context):
    print(json.dumps(event))  # debug log

    # CloudFormation template fragment
    fragment = event.get("fragment", {})

    # ⚠️ Example: không modify gì, trả về nguyên template
    return {
        "requestId": event["requestId"],
        "status": "success",
        "fragment": fragment
    }
