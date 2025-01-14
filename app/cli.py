import time
import os
import yaml

from sqlalchemy import exc
from app import search_client, index
from .models import Category, Language, Resource


def import_resources(db):   # pragma: no cover
    # Step 1: Get data
    with open('resources.yml', encoding='utf-8') as f:
        data = yaml.full_load(f)

    # Step 2: Uniquify resources
    unique_resources = remove_duplicates(data)

    # Step 3: Get existing entries from db_session
    try:
        resources_list = Resource.query.all()
        languages_list = Language.query.all()
        categories_list = Category.query.all()

        # Convert to dict for quick lookup
        existing_resources = {r.key(): r for r in resources_list}
        language_dict = {l.key(): l for l in languages_list}
        category_dict = {c.key(): c for c in categories_list}
    except AttributeError as e:
        print('-------> EXCEPTION OCCURED DURING DB SETUP')
        print('-------> Most likely you need to set the '
              '"SQLALCHEMY_DATABASE_URI"')
        print(f'-------> Exception message: {e}')
        return

    # Step 4: Create/Update each resource in the db_session
    for resource in unique_resources:
        # Note: modifies the category_dict in place (bad?)
        resource['category'] = get_category(resource, category_dict)
        # Note: modifies the language_dict in place (bad?)
        resource['languages'] = get_languages(resource,
                                              language_dict)
        existing_resource = existing_resources.get(resource['url'])

        if existing_resource:
            resource == existing_resource or \
                        update_resource(resource, existing_resource)
        else:
            create_resource(resource, db)

    try:
        db.session.commit()
    except exc.SQLAlchemyError as e:
        db.session.rollback()
        print('Flask SQLAlchemy Exception:', e)
        print(resource)
    except Exception as e:
        db.session.rollback()
        print('exception', e)
        print(resource)


def remove_duplicates(data):
    unique_resources = []
    resource_dict = {}
    for resource in data:
        if not resource_dict.get(resource['url']):
            resource_dict[resource['url']] = True
            unique_resources.append(resource)
        else:
            print(f"Encountered a duplicate resource "
                  f"in resources.yml: {resource['url']}")
    return unique_resources


def get_category(resource, category_dict):
    category = resource.get('category')

    if not category_dict.get(category):
        category_dict[category] = Category(name=category)

    return category_dict[category]


def get_languages(resource, language_dict):
    langs = []

    # Loop through languages and create a new Language
    # object for any that don't exist in the db_session
    for language in resource.get('languages') or []:
        if not language_dict.get(language):
            language_dict[language] = Language(name=language)

        # Add each Language object associated with this resource
        # to the list we'll return
        langs.append(language_dict[language])

    return langs


def create_resource(resource, db):
    new_resource = Resource(
        name=resource['name'],
        url=resource['url'],
        category=resource['category'],
        languages=resource['languages'],
        paid=resource.get('paid'),
        notes=resource.get('notes', ''),
        upvotes=resource.get('upvotes', 0),
        downvotes=resource.get('downvotes', 0),
        times_clicked=resource.get('times_clicked', 0))

    try:
        db.session.add(new_resource)
    except Exception as e:
        print('exception', e)


def update_resource(resource, existing_resource):   # pragma: no cover
    existing_resource.name = resource['name']
    existing_resource.url = resource['url']
    existing_resource.category = resource['category']
    existing_resource.paid = resource.get('paid')
    existing_resource.notes = resource.get('notes', '')
    existing_resource.languages = resource['languages']


def reindex_all():  # pragma: no cover
    query = Resource.query
    indicies = search_client.list_indices()
    for ind in indicies['items']:
        if ind['name'] == os.environ.get('INDEX_NAME'):
            db_list = [u.serialize_algolia_search for u in query.all()]
            index.replace_all_objects(db_list)
    print("Finished Reindexing.")


def register(app, db):  # pragma: no cover
    @app.cli.group()
    def db_migrate():
        """ migration commands"""
        pass

    @app.cli.group()
    def algolia():
        """Reindex Commands"""
        pass

    @db_migrate.command()
    def init():
        print(db)
        print("Populating db from resources.yml...")
        start = time.perf_counter()
        import_resources(db)
        stop = time.perf_counter()
        print("Finished populating db from resources.yml")
        print(f"Elapsed time: {(stop-start)/60} [min]")

    @db_migrate.command()
    def create_tables():
        db.create_all()

    @algolia.command()
    def reindex():
        reindex_all()
