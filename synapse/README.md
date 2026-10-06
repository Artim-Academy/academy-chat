# artim_lms – Synapse-Modul für Artim Academy

Synchronisiert Rollen, Kurse und Einschreibungen aus dem Artim Academy LMS nach Matrix und setzt das Rechtemodell durch.

## Was das Modul macht

- **Sync** (alle 5 Minuten und beim ersten Login eines neuen Users) über die Devhub-API des LMS:
  `/dev-api/v1/admin/users`, `/dev-api/v1/courses/courses`, `/dev-api/v1/students/enrollments`.
- **Pro LMS-Kurs** gibt es genau einen Space `#course-<courseId>` mit dem Namen des Kurses. Er gehört dem Bot `@lms-sync`.
  - Trainer und eingeschriebene Studierende werden automatisch in den Space aufgenommen.
  - Räume im Space legen die Trainer selbst an. Der Bot wird dabei eingeladen, damit er die Rollen durchsetzen kann.
  - Wer nicht mehr im Kurs ist, fliegt aus dem Space und allen Räumen darin.
- **Power-Levels:** In allen Kursräumen setzt der Sync die User-Level neu (Bot/Admin 100, Trainer 50, Studierende 0).
  - Raum-Einstellungen, die ein Trainer gesetzt hat, bleiben unangetastet, z. B. Schreiben für Studierende freigeben.
- **Account-Data:** Der Sync schreibt `de.artim_academy.lms_sync`. Daraus liest die Settings-Seite „Artim Academy“ im Client.

## Rechtemodell

Admin (LMS-Admin) darf immer alles.

- **Trainer (global):** jeder mit der Akademie-Rolle `trainer`.
- **Trainer (kursbezogen):** der Ersteller des LMS-Kurses.
- **Student (kursbezogen):** eingeschrieben mit Status `active` oder `paused`.

| Aktion | Trainer global | Trainer Kurs | Student Kurs |
| --- | :-: | :-: | :-: |
| Räume erstellen (im eigenen Kurs-Space) | | ✓ | |
| Spaces erstellen | | | |
| DMs starten | ✓ | | ✓ (nur gemeinsame Kurse) |
| Nutzerverzeichnis durchsuchen | ✓ | | ✓ (nur gemeinsame Kurse) |
| Einladen | | ✓ | ✓ |
| Kicken, bannen, Rechte ändern | | ✓ | |
| Nachrichten schreiben | | ✓ | nur wenn der Trainer den Raum freigibt |
| Fremde Nachrichten löschen | | ✓ | |
| @room, anpinnen, Umfragen, Uploads | | ✓ | ✓ |
| Name/Thema/Avatar, Beitritt/Sichtbarkeit, Space-Räume, Widgets | | ✓ | |
| Calls (auch Jitsi-Widgets) | gesperrt | gesperrt | gesperrt |
| Profil, Passwort, E-Mail, Telefon, Account löschen | LMS ist Quelle | LMS ist Quelle | LMS ist Quelle |

In globalen Räumen (`global_rooms`, z. B. `#academy`) schreiben und einladen nur Admins.

## Voraussetzungen im LMS

1. Ein aktiver Devhub-Client, z. B. `academy-chat-sync`, mit den API-Scopes `lms.admin.users:read`, `lms.courses:read` und `lms.students.enrollments:read`.
2. `DEVHUB_SYNC_TOKEN` ist am `lms-backend` gesetzt.
3. Ein LMS-Admin der Akademie als Service-User (`service_user_id`). In seinem Namen werden die Tokens ausgestellt.

## homeserver.yaml

```yaml
modules:
  - module: artim_lms.ArtimLms
    config:
      lms_base_url: "https://api.artim-academy.de"
      tenant_id: "<Mongo-Id der Akademie>"
      sync_token: "<DEVHUB_SYNC_TOKEN>"
      client_id: "academy-chat-sync"
      service_user_id: "<LMS-User-Id eines Admins>"
      extra_admins: ["@breakglass:artim-academy.de"]
      global_rooms: ["#academy:artim-academy.de"]

# The LMS profile is the only source for name, avatar and contact details.
enable_set_displayname: false
enable_set_avatar_url: false
enable_3pid_changes: false

user_directory:
  enabled: true
  search_all_users: true

oidc_providers:
  - idp_id: artim
    # ...
    # no user_profile_method: groups/tenants only exist in the id_token, not in userinfo
    user_mapping_provider:
      config:
        subject_claim: "sub"
        localpart_template: "{{ user.sub }}"
        display_name_template: "{{ user.name }}"
        email_template: "{{ user.email }}"
        picture_template: "{{ user.picture }}"
    update_profile_information: true
```

Der Passwort-Login bleibt in Synapse an. Das Modul lässt ihn aber nur für `extra_admins` durch (Notzugang).

## docker-compose

Das Modul muss im Synapse-Container im `PYTHONPATH` liegen:

```yaml
  synapse:
    environment:
      PYTHONPATH: /data/modules
    # ./data/synapse is already mounted to /data, copy artim_lms/ to ./data/synapse/modules/artim_lms
```

## Tests

```sh
cd synapse
python3 -m unittest discover -s tests -t .
```

`tests/test_module.py` läuft nur, wenn `matrix-synapse` installiert ist (`pip install matrix-synapse==1.162.0`).
