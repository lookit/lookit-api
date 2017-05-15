











# TODO
- Add the ability to filter the queue of studies in an organization by their status.
- Make sure to add LoginRequiredMixin to all views that need it
- Make sure to add permission requirements to all exp views
- Add login, logout, forgot password, change user information #web
- Collaborator creation
  - **exp website**
  - Organization admin enters user information
  - Creates and/or assigns groups to user
- Study manipulation
  - **exp website**
  - List of current studies (within the org, unless admin)
    - Allow moving studies through workflow
  - Create, either build or upload
    - Build
      - List frames / list available frames
        - Allow reordering, adding, and removing
    - Upload
      - Allow uploading built project
  - Viewing of study data
- Response gathering
  - API for response gathering
  - Data export
  - JSON => CSV
- Setup templated emails functionality triggered by state change
- Wire up wolfkrow call backs.
  - especially permission checks
- s3 module
  - CRUD folders for video
  - Generation of time-limited urls to access files
  - Could potentially cache exported data there; #STRETCH
  - Collaborators in Orgs should be able to access things only inside of their organization or group's folders
- Lookit website
  - Static assets
  - dynamic sections?
    - flatpages?
