# Zwift Map pour Home Assistant

Affiche la **route Zwift que tu roules**, en direct, sur un écran Home Assistant visible depuis le vélo : carte du parcours avec ta position, profil d'altitude, pente, distance restante et puissance sur la couleur de ta zone. Pensé pour un écran mural (NSPanel Pro 120, tablette…) face au home trainer.

<p align="center">
  <img src="docs/card-portrait.png" width="300" alt="Carte en portrait (format NSPanel Pro 120)">
  <img src="docs/card-landscape.png" width="520" alt="Carte en paysage">
</p>

<sub>Captures réalisées avec un parcours simulé.</sub>

## Ce que ça fait

- **Intégration `zwift_map`** : interroge Zwift toutes les 2 s pendant que tu roules (toutes les 30 s sinon) et lit les champs que les autres intégrations ignorent, en particulier l'**identifiant de la route** et le **monde**.
- **Progression réelle sur la route** : la distance de Zwift est celle de toute la sortie. L'intégration repart de zéro quand une route est choisie, déduit le **lead-in** (différent en événement et en free ride) et compte les **tours**. Exemple : 10 km de free ride puis 1 km sur une route de 20 km donnent **5 %**, pas 55 %.
- **Tracé enregistré pendant tes sorties** : à chaque passage, la position et l'altitude envoyées par le jeu sont enregistrées tous les 10 m dans `/config/zwift_map/tracks/<route_id>.json`. La première fois, la carte se dessine au fil de la sortie. Ensuite, la route complète s'affiche dès le départ, même sans Internet.
- **Carte Lovelace `zwift-map-card`** : servie directement par l'intégration, rien d'autre à installer.

## Installation

1. HACS → ⋮ → *Dépôts personnalisés* → `https://github.com/Lobwick/zwift-map-home-assistant`, catégorie **Intégration**.
2. Installe **Zwift Map** et redémarre Home Assistant.
3. *Paramètres → Appareils et services → Ajouter une intégration → Zwift Map*, puis saisis ton compte Zwift.

### Entités

| Entité | Contenu |
|---|---|
| `binary_sensor.zwift_map_riding` | Tu es sur Zwift |
| `sensor.zwift_map_route` | Nom de la route (attributs : distance, dénivelé, lead-in, couverture du tracé) |
| `sensor.zwift_map_world` | Monde (Watopia, France…) |
| `sensor.zwift_map_route_progress` | Progression sur la route (%) |
| `sensor.zwift_map_route_distance` | Distance parcourue sur la route (km) |
| `sensor.zwift_map_remaining_distance` | Distance restante (km) |
| `sensor.zwift_map_lap` | Tour en cours |
| `sensor.zwift_map_gradient` | Pente (%) |
| `sensor.zwift_map_live` | Phase (`free_ride`, `lead_in`, `on_route`…) avec toutes les données en direct en attributs, non enregistrées dans l'historique. C'est la source de la carte. |

## La carte

```yaml
type: custom:zwift-map-card
entity: sensor.zwift_map_live
# Couleur de zone : reprend celle de l'intégration Zwift si elle est installée…
zone_color_entity: light.zwift_<prénom>_power_zone_color
# …ou la calcule à partir de ta FTP
ftp_entity: sensor.zwift_<prénom>_ftp   # ou ftp: 252
layout: auto          # auto | portrait | landscape
map_rotate: 0         # 0 | 90 | 180 | 270 pour orienter la carte comme dans Zwift
map_mirror: false
show_map: true
show_profile: true
show_stats: true
```

Sur un écran dédié, mets la carte seule dans une vue en mode **Panneau** : elle occupe tout l'écran, et la carte du parcours prend l'espace libre. Le format portrait est prévu pour les 750×1334 du NSPanel Pro 120.

## Limites

- **API non officielle** : c'est celle qu'utilise Zwift Companion. Zwift peut la modifier sans prévenir.
- **Requêtes limitées** : si une autre intégration Zwift interroge aussi le serveur toutes les 2 s, Zwift peut répondre « trop de requêtes » (429). Zwift Map ralentit alors automatiquement, puis revient à 2 s.
- **À valider en conditions réelles** : le champ « route » (n° 39) est documenté par la communauté. Son comportement en événement (group ride, course) reste à confirmer, tout comme l'orientation de la carte (`map_rotate` / `map_mirror` permettent de la corriger).
- **Free ride sans route** : pas de route, donc pas de carte de parcours. Les compteurs et la pente restent affichés.
- **Redémarrage de Home Assistant en pleine sortie** : la progression reprend là où elle en était, mais seulement sur la même route.

## Crédits

- Catalogue des routes (noms, distances, dénivelés, lead-in) : [zwift-data](https://github.com/andipaetzold/zwift-data) © Andi Pätzold, licence MIT. Pour le régénérer : `scripts/build_routes.mjs`.
- Description des champs du protocole Zwift : travail de rétro-ingénierie de la communauté, notamment le projet [zwift-offline](https://github.com/zoffline/zwift-offline).
- Projet non affilié à Zwift. « Zwift » est une marque de Zwift, Inc.

## Développement

```bash
pip install pytest-homeassistant-custom-component
pytest            # tests/ : logique pure ; tests/ha : intégration chargée dans Home Assistant
```
