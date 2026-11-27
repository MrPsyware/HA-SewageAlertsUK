# List Sewage Alerts UK in the Marketplace

Home Assistant 2026.11 introduced the built-in Marketplace. It shares its catalogue with HACS, so one submission covers both. Users can install from the repository link while the submission is under review. [Home Assistant catalogue guide](https://contributors.home-assistant.io/marketplace/guides/catalog/)

## Prepare the release

1. Confirm the public GitHub repository has a description, topics, issues enabled and a recognised open-source licence. This project uses MIT. The root `hacs.json` declares GB coverage, and `custom_components/sewage_alerts_uk/` contains the integration manifest and `brand/icon.png`. HACS accepts the bundled icon. [Integration requirements](https://www.hacs.xyz/docs/publish/integration/)
2. Update the manifest version and changelog for the release. Push the reviewed changes and wait for **Tests and lint**, **HACS** and **Hassfest** on the release commit. The HACS job must pass with every check enabled. Save the direct GitHub job links for HACS and Hassfest. [Project validation runs](https://github.com/MrPsyware/HA-SewageAlertsUK/actions/workflows/validate.yml)
3. Once the checks pass, publish a full GitHub release from that commit, tagged `vX.Y.Z` to match the manifest. This project installs directly from the tag and needs no separate ZIP asset. Verify the published release installs using **Settings → Marketplace → Add from link**. [Project releases](https://github.com/MrPsyware/HA-SewageAlertsUK/releases)

## Submit the catalogue change

1. As the owner or a major contributor, fork `hacs/default` to your personal GitHub account. Create a new branch from upstream `master`.
2. In the root `integration` JSON list, insert `"MrPsyware/HA-SewageAlertsUK"` in alphabetical order. [Integration list](https://github.com/hacs/default/blob/master/integration)
3. Open a pull request against `hacs/default:master` with **Allow edits by maintainers** enabled. Complete every item in the template and supply three links: the published release, the successful HACS job and the successful Hassfest job. Leave reviewer assignment to the HACS team. [Pull request template](https://github.com/hacs/default/blob/master/.github/PULL_REQUEST_TEMPLATE.md)
4. Follow the automated checks and address feedback on the same branch. Reviews can take months. After merge, the next catalogue scan makes the integration discoverable. [Inclusion and review process](https://www.hacs.xyz/docs/publish/include/)
