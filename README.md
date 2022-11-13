# option_wheel_tracker

Use `pip install -r requirements.dev` to download dependencies. Then `python manage.py runserver` to start the server

## Requirements
1. Python 3.9
2. Poetry: https://python-poetry.org/docs/#installing-with-the-official-installer


# Local Development

## Create environment and install depdendencies
`poetry install`

## Update dependencies:
`poetry update`

## Run local dev server:
`poetry run python manage.py runserver`

# Deployment
1. Install `flyctl` https://fly.io/docs/flyctl/installing/
2. Run `fly deploy`

# Production server
ssh to the prod server:
`fly ssh console -a optionwheel`

Or to get a bash shell, just run:
`bash prod_server`


# Database

## Migrate database from Heroku
https://fly.io/docs/postgres/getting-started/migrate-from-heroku/#provision-and-deploy-a-postgres-app-to-fly

1. Connect to db app console
`fly ssh console -a optionwheeldb`
2. Dump and restore DB
`pg_dump -Fc --no-acl --no-owner -d $HEROKU_DATABASE_URL | pg_restore --verbose --clean --no-acl --no-owner -d $DATABASE_URL/optionwheel`
3. Verify transfer:
* `fly pg connect -a optionwheeldb -d optionwheel`
* `\dt`

## Connect to production DB:
`fly pg connect -a optionwheeldb -d optionwheel`

## Run locally against production DB
1. Proxy to local port 5432 in a seperate tab
`flyctl proxy 5432 -a optionwheeldb`
2. While proxy, set the following in your .env file at the root of the project
`DATABASE_URL="postgres://postgres:<password>@localhost:5432/optionwheel"`

# Logs
Run:
`flyctl logs`
