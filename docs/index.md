# AI Agent

AI Agent is a QGIS 4 plugin that works on your project from plain-language
requests. It reads the project, calls tools, looks at the results and decides
the next step. Changes wait in a plan until you press **Apply**.

## What it does

Nineteen domains, 90 tools:

| Domain | Example request |
| --- | --- |
| `inspect` | what layers do I have? |
| `project` | add an OSM basemap |
| `style` | colour the districts by population |
| `processing` | build a 500 m buffer around the schools |
| `osm` | download the cafes in Tver |
| `data` | find a cloud-free Sentinel-2 image of this area |
| `draw` | put a point at 55.75, 37.62 |
| `edit` | delete the features I selected |
| `fields` | add a virtual field with the area in hectares |
| `layout` | make an A4 map with a legend and export it to PDF |
| `python` | runs a PyQGIS snippet you read and approve first |
| `web` | read this documentation page |
| `annotations` | add a note to the map |
| `three_d` | open a 3D view of this project |
| `tables` | join this CSV to the districts by code |
| `sql` | how many schools are in each district? |
| `charts` | chart population by district |
| `plugins` | which plugin can make a web map? |
| `quality` | check my data for errors |

On a model that accepts images, the agent also looks at the rendered map.
After you press Apply it checks the result and proposes fixes when something
did not work.

## How changes are applied

- Tools that only read the project run at once.
- Tools that change the project wait in a plan card until you press
  **Apply**. **Cancel** drops the whole plan.
- Tools that contact a web service ask before each call.
- Steps that edit or delete data in place, run Python or run another
  plugin's code ask once more.

In Auto mode the plan applies itself, except when it holds one of those
steps.

## What you need

- QGIS 4.0 or newer.
- A language model: any OpenAI-compatible endpoint or the Anthropic API.
  Local servers such as Ollama and LM Studio need no key.

Everything the agent reads goes to the model you configure. Read
[Data and privacy](privacy.md) before you connect a remote provider.

Start with [Setup](SETUP.md), then see [Usage](usage.md). The interface is in
English and Russian and follows the QGIS language.
