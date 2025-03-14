# Process Photos 

Takes all photos from import folder OR from originals folder (copied to the import folder by the tool), checks files to see if there is an exif date.  

If no exif date if found, then lists the photos along with possible guesses of the date (using filename, filepath, filedate).  Allows you to write the date to the files, etc.  Edited files are dumped into the export folder.  

## Usage: 

#### Docker Compose:

```docker
services:
  web:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - /home/ben/docker/processphotos/import:/import
      - /home/ben/docker/processphotos/export:/export
      - /home/ben/docker/processphotos/config:/config
      - /home/ben/docker/processphotos/originals:/originals
      - /home/ben/docker/processphotos/logs:/logs
    environment:
      - FLASK_ENV=development
      - FLASK_DEBUG=1
```