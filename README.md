<!-- markdownlint-disable MD041 -->
> "Give a man a fish, you'll feed him for a day. Teach a man to fish, you'll feed him for a lifetime".
> Give an entire club 2 Codex Pro accounts, and this is what they'll vibecode out.

# HCMUSEC Tournament Registration Hub

**Currently on testing at** <https://staging.giaidau.hcmusec.com>. We welcome your feedback and recommendations in the Issues tab. Do note however:

> [!CAUTION]
>
> PLEASE DO NOT ENTER ANY SENSITIVE INFORMATION REAL INFO OR MAKE ACTUAL PAYMENTS!

## About

Source code for the Tournament Registration Hub, developed by VNUHCM - University of Science Esports Club, with help and consulting/guidance from OpenAI's Codex.

> [!NOTE]
>
> Some of the features of this project has been finished, however, others are not.
> Due to this, bugs, issues and instability might occur.
>
> Report the bugs and improvements to the Issues tab, except security issues, which should be emailed directly to [hcmusec@gmail.com](mailto:hcmusec@gmail.com).

## Tech Stack

- **Frontend**: Svelte 5, SvelteKit 2
- **Styling**: TailwindCSS, Shadcn-Svelte with some custom styling.
- **Backend**: Django 6, Django REST Framework, Django-Unfold Admin
- **Database**: PostgreSQL
  - *Note on Postgres*: On development, we tested on Postgres 18, but on deployment we used Postgres 17. It's better if you consult [Django's Docs on Database](https://docs.djangoproject.com/en/6.1/ref/databases/#postgresql-notes) for the latest supported version.
- **Hosting**: Own VPS (Oracle ARM Ampere A1) with Docker Compose.

### Requirements

- [mise](https://mise.jdx.dev/)
- Docker with Docker Compose
- Git

Clone the repository:

```sh
git clone https://github.com/USEC-US/registration-hub.git
cd registration-hub
```

Install the required runtimes and project dependencies:

```sh
mise install
mise run install
```

Create the local environment files:

```sh
cp server/.env.example server/.env
cp web/.env.example web/.env
```

For local development, set:

```env
DEBUG=True
```

in `server/.env`.

Start PostgreSQL and apply the database migrations:

```sh
mise run db:up
mise run server:migrate
```

Start both the Django and SvelteKit development servers:

```sh
mise run dev
```

The development servers are available at:

- Frontend: <http://localhost:5173>
- Backend API: <http://localhost:8000>
- Django Admin: <http://localhost:8000/admin/>

Other useful commands:

```sh
mise run check
mise run lint
mise run format
mise run test
```

## Running with Docker Compose

The repository currently contains two Compose configurations:

- `compose.yaml` — local PostgreSQL for development.
- `compose.staging.yaml` — the HCMUSEC public staging deployment.

The staging configuration uses the published container image:

```text
ghcr.io/usec-us/registration-hub:staging
```

and is designed specifically for HCMUSEC infrastructure, including its domain and SWAG reverse-proxy network.

A generic Compose configuration for self-hosted deployments is not yet provided, however you can get away with modifying the default [`compose.staging.yaml`](./compose.staging.yaml) file. If you decided to go for it:

1. Set up your DB by creating a new user and a new database. For example:
    - *Note*: Your database password must not exceed 99 characters. See [here for why](https://www.postgresql.org/message-id/09512C4F-8CB9-4021-B455-EF4C4F0D55A0@amazon.com).

```sql
-- Replace tnmt_reg_hub_staging and the password with your own.
CREATE USER tnmt_reg_hub_staging WITH PASSWORD 'no-more-than-99-characters-due-to-postgres-limitations';
CREATE DATABASE tnmt_reg_hub_staging WITH OWNER tnmt_reg_hub_staging;
```

1. Copy [`docker.env.example`](./.docker.env.example) into a separate `.env` file and customize the fields.
2. Copy [`compose.staging.yaml`](./compose.staging.yaml), rename to `compose.yaml` or `docker-compose.yaml`, and do a search and replace where we have our domain `staging.giaidau.hcmusec.com`.
   - TODO: add this as Dotenv variable instead.
3. Run `docker compose up` to start the containers with logs, or `docker compose up -d` to run them in the background.

## License

This project is licensed under the **Affero General Public License 3 (AGPL-3.0)**.
