#!/bin/bash
# Script to set up Mastodon test instance with a test user and application

set -e

echo "Setting up Mastodon test instance..."

# Wait for Mastodon to be fully ready
echo "Waiting for Mastodon to be ready..."
for i in {1..30}; do
    if docker compose exec -T mastodon-web wget -q --spider --proxy=off localhost:3000/health 2>/dev/null; then
        echo "Mastodon is ready!"
        break
    fi
    echo "Waiting for Mastodon... ($i/30)"
    sleep 2
done

# Create test user
echo "Creating test user..."
docker compose exec -T mastodon-web bin/tootctl accounts create \
    testuser \
    --email=test@localhost \
    --confirmed \
    --role=Owner \
    || echo "Test user may already exist"

# Create OAuth application for testing
echo "Creating OAuth application..."
docker compose exec -T mastodon-web rails runner '
app = Doorkeeper::Application.find_or_create_by!(
  name: "POSSE Test Client",
  redirect_uri: "urn:ietf:wg:oauth:2.0:oob",
  scopes: "read write follow",
  confidential: true
)
puts "Application ID: #{app.id}"
puts "Client ID: #{app.uid}"
puts "Client Secret: #{app.secret}"
' > /tmp/mastodon_app_info.txt

cat /tmp/mastodon_app_info.txt

# Get test user account
echo "Getting test user account..."
USER_ID=$(docker compose exec -T mastodon-web rails runner '
user = User.find_by(email: "test@localhost")
if user && user.account
  puts user.account.id
else
  puts "ERROR: User not found"
  exit 1
end
')

echo "Test user account ID: $USER_ID"

# Create access token for test user
echo "Creating access token..."
docker compose exec -T mastodon-web rails runner "
app = Doorkeeper::Application.find_by(name: 'POSSE Test Client')
user = User.find_by(email: 'test@localhost')

if user && user.account && app
  token = Doorkeeper::AccessToken.create!(
    application_id: app.id,
    resource_owner_id: user.id,
    scopes: 'read write follow',
    expires_in: nil
  )
  puts token.token
else
  puts 'ERROR: Could not create token'
  exit 1
end
" > /tmp/mastodon_test_token.txt

TOKEN=$(cat /tmp/mastodon_test_token.txt)
echo "Access token created: $TOKEN"

# Save token to file that tests can read
mkdir -p secrets
echo "$TOKEN" > secrets/mastodon_test_access_token.txt

echo "Setup complete!"
echo "Test instance URL: http://localhost:3000"
echo "Test user: testuser@localhost"
echo "Access token saved to: secrets/mastodon_test_access_token.txt"
echo ""
echo "You can now run tests with: docker compose --profile test run --rm test"
