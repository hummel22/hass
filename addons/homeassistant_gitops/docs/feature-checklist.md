# YAML Modules Feature Checklist

This file tracks planned YAML Modules enhancements. Items are grouped by priority and
should be updated as work lands.

## Implement

- Better id management: prefer names and ids for stable matching.
- Build new packages(or append to existing packages) from unassigned units .
    - when you click on a file, in the sidebar below the file clicked, a new row of indented cards should show up it should show the top level items of the yaml (for know apply same logic to all types, we may need to implememt logic per type)
    - clicking on an item should show just that item in the editor
    - a new button in the center card should be used to save or move to a package, also a button to delete from packages
    - this will open a new popup, 
        - here a user can select froma dropdown a list of packages to move the item to
        - or can create a new package or a button to move to one off package - (will need to set file name)
    - bug in naming in drop down on module browser
        - the domain sectino is wrong, domain files are the entire Ui generated top level files, change it this
        - create a new section call unassigned and list all the unassigned yaml files there
- Export entities/devices/areas to YAML for version-controlled registry data.
  - add a new tab called export to the UI
  - on the export page, have seperate tabs
    - one for entities
    - one for areas
  - have the ability to export entities to yaml files 
    - we will write this data to system/entities.csv
        - this will be a csv file
        - each entity will be a row
        - device name, device id, entity name, entity id, entity domain, integration, type, unit,area, tbd
        - allow the user to blacklist, certian integrations, (dont read those entities)
  - export area data
    - area name, floor
    - file in /system/area.csv
  - display current data in table form per tab type
    
- Local YAML validation helper: lightweight pre-commit or CLI validator.
    - create a cli
    - in the settings menu have to option to install cli to repo in .gitops/cli folder
    - the cli will run the same logic as sync
    - it will validate the yamls in packaage and one off
    - it build packages and one offs into domain yamls
    - it should be very light weight as possible, 
- Add a preview sync button
    - two seperate dections
        - show changes made to domain files from packages
        - show changes made to pacakges and one offs from changes in domain files


TODo 
- Optional mapping file versioning: allow users to ignore `.gitops/mappings/*` in Git.
- GitOps templates: inject shared objects into multiple YAML locations during sync.
- add files to .gitignore
- export groups 
- - support creating groups though modulescreate a dashboard to manage groups - add, delete, edit groups, 
    - ignore certian groups
        - mangage only gitops groups
        - users can import a ha group to be manged be gitops, so default ignored


