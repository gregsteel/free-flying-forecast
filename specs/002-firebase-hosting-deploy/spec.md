# Feature Specification: Firebase Hosting Deployment

**Feature Branch**: `002-firebase-hosting-deploy`

**Created**: 2026-10-03

**Status**: Superseded on 2026-10-04: the owner chose GitHub Pages instead (the existing git publisher, `publish.py`, pushes the site to a `gh-pages` branch). Kept for reference; nothing here is built and none of it is needed for GitHub Pages. If Firebase is wanted later, this spec is the starting point.

**Input**: User description: "Firebase deployment for Free Flying Forecast: publish the static site (the out/ directory the pipeline already produces) to Firebase Hosting in the existing project 'free-flying-forecast' (console: https://console.firebase.google.com/project/free-flying-forecast/overview), automatically after each successful run, unattended from the owner's iMac container, within the free plan. Spec only: no build yet."

**Builds on**: [001 Free Flying Forecast](../001-free-flying-forecast/spec.md). That feature produces the page and `forecast.json`; this one makes them public. It replaces the interim "push to a git remote" publisher described there (001 FR-005a).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Pilots reach the forecast at one stable address (Priority: P1)

A pilot opens the Free Flying Forecast at its public web address on their phone, at any hour, whether or not the owner's computer is on. The page loads fast over a mobile connection, over a secure connection, and shows the most recent successful forecast.

**Why this priority**: Without a public, always-available address the forecast is useful only to its owner. This is the point of the whole deployment.

**Independent Test**: With a forecast already published, open the public address from a phone on mobile data while the owner's computer is switched off; the forecast loads, the "updated" time is the latest run, and the connection is secure.

**Acceptance Scenarios**:

1. **Given** a published forecast, **When** a pilot opens the public address, **Then** the page loads over a secure connection and shows the latest successful run's forecast.
2. **Given** the owner's computer is asleep or off, **When** a pilot opens the address, **Then** the forecast is still served.
3. **Given** a pilot opens a web address that does not exist on the site, **When** the page responds, **Then** they see a short "not found" page in the same style with a link back to the forecast.
4. **Given** a pilot who opened the page earlier in the day, **When** a newer forecast has been published and they reload, **Then** they see the newer forecast within a few minutes, not hours later.

---

### User Story 2 - Each successful run goes live by itself, and a failed one never does (Priority: P1)

After every successful daily run the new page goes live automatically with no action from the owner. If anything fails (the run, the checks, or the upload), the previous forecast stays live, the owner can see what went wrong, and visitors never see a half-updated or broken page.

**Why this priority**: The forecast must refresh unattended (001 US2), and a bad deployment that replaces a good page would be worse than a stale one.

**Independent Test**: Run the deployment with a good page, then with a deliberately broken page and with the network cut mid-upload; confirm the first goes live and the others leave the live page unchanged and are recorded as failures.

**Acceptance Scenarios**:

1. **Given** a run finishes successfully, **When** the deployment step runs, **Then** the new page becomes live without any manual step.
2. **Given** the page fails the pre-deployment checks, **When** the deployment step runs, **Then** nothing is deployed and the failure is recorded with the reason.
3. **Given** the upload is interrupted or the hosting service is unavailable, **When** a visitor opens the site, **Then** they still see the previous complete forecast.
4. **Given** the same forecast cycle was already deployed, **When** the deployment step runs again, **Then** it does not deploy a second time.
5. **Given** a deployment finished, **When** the system checks the public address, **Then** it confirms the live page is the one just deployed, and records a failure if it is not.

---

### User Story 3 - The owner can preview and roll back safely (Priority: P2)

Before a change to the page design or rules goes live, the owner can look at it at a temporary address that is not linked from the site. If a live release turns out to be wrong, the owner can put the previous release back quickly without rebuilding anything.

**Why this priority**: The page changes often while the product is young; recovery must be quick and need no special skills.

**Independent Test**: Deploy a preview, confirm the live site is unaffected; make a deliberately bad release live, then restore the previous one and confirm visitors see the earlier forecast.

**Acceptance Scenarios**:

1. **Given** a changed page, **When** the owner deploys a preview, **Then** it is reachable at a temporary address and the live site is unchanged.
2. **Given** a bad release is live, **When** the owner restores the previous release, **Then** visitors see the earlier release within five minutes.
3. **Given** many releases have been made, **When** the owner wants to go back, **Then** at least the ten most recent releases are still available.

---

### User Story 4 - Cost, access and privacy stay under control (Priority: P3)

The deployment costs nothing, uses only the access it needs, stores no secrets in the code or image, and adds no tracking of visitors.

**Why this priority**: These are the constraints that keep a hobby project safe to leave running, but they do not change what pilots see.

**Independent Test**: Review the repository, container image and run logs for credentials; confirm the project is on the free plan; check the live responses for the required security headers and the absence of tracking.

**Acceptance Scenarios**:

1. **Given** the repository, the container image and the logs, **When** they are searched for credentials, **Then** none are found.
2. **Given** the credentials the deployment uses, **When** their permissions are reviewed, **Then** they allow publishing the site and nothing else in the project.
3. **Given** the live site, **When** its responses are inspected, **Then** they carry the agreed security headers and the page includes no analytics or tracking.
4. **Given** the free plan's limits, **When** traffic is at the expected level, **Then** usage stays well under the limits and no charge can occur.

---

### Edge Cases

- The upload is interrupted part way, or the network drops during the deployment.
- The hosting service has an outage, or rejects the upload.
- The credentials have been revoked, expired or rotated.
- The free plan's monthly transfer or storage limit is reached (the site stops responding until the limit resets).
- The owner's computer is offline at the time of the run, so the deployment waits for the next run.
- Two runs overlap and both try to deploy.
- The page is empty, truncated, or missing the required credits and advisory notice.
- The live page cannot be confirmed after deployment (for example the address is cached or the wrong release is serving).
- The weather station or the current-conditions provider is unreachable (the page must still be deployable and usable; those parts are optional).
- A previous release is needed but was removed.
- The project's plan or settings are changed outside this system.

## Requirements *(mandatory)*

### Functional Requirements

**Target and release**

- **FR-001**: The system MUST publish the site to Firebase Hosting in the existing project `free-flying-forecast`, whose default public addresses are `https://free-flying-forecast.web.app` and `https://free-flying-forecast.firebaseapp.com`.
- **FR-002**: The project and site identifiers, and the folder to publish, MUST be held in configuration, not written into code.
- **FR-003**: Each deployment MUST be a new release in which visitors see either the whole previous page or the whole new one, never a mixture.
- **FR-004**: The system MUST publish exactly what the forecast pipeline produced for the run (the page and `forecast.json`) and nothing else from the working folders.
- **FR-005**: The site MUST be served only over a secure connection, and web addresses that do not exist MUST show a short "not found" page in the site's style with a link back to the forecast.

**Automation and safety**

- **FR-006**: After every successful forecast run, the system MUST deploy the new page automatically, unattended, from the owner's container, with no browser login or prompt.
- **FR-007**: The system MUST NOT deploy when the run failed, and MUST check the page before deploying: the page exists and is not empty, `forecast.json` is valid and matches the run, the generated time is present, and the credits, advisory notice and BoM warnings link are present. A page that fails any check MUST NOT be deployed.
- **FR-008**: Whenever any step of a deployment fails, the previous release MUST remain live, and the failure and its reason MUST be recorded.
- **FR-009**: The system MUST NOT deploy the same forecast cycle twice, and MUST prevent two deployments from running at once.
- **FR-010**: After deploying, the system MUST fetch the public address and confirm it is serving the page just deployed (by its generated time), and MUST record a failure if it is not.
- **FR-011**: A failed deployment MUST NOT stop the next scheduled run from trying again.
- **FR-012**: Each deployment MUST be recorded alongside the run: time, forecast cycle, outcome, release identifier, number of files, bytes uploaded, duration and the address checked.
- **FR-013**: The system MUST keep one owner-only status (not on the public site) showing the time, forecast cycle and outcome of the latest deployment and the time of the latest success, and MUST flag clearly when the latest attempt failed or when no deployment has succeeded for more than 36 hours.

**Preview and rollback**

- **FR-014**: The owner MUST be able to deploy the current page to a temporary preview address without changing the live site.
- **FR-015**: The owner MUST be able to restore the previous live release in under five minutes without regenerating anything.
- **FR-016**: At least the ten most recent releases MUST remain available for restoring.

**Caching and security headers**

- **FR-017**: A new forecast MUST be visible to returning visitors within five minutes of its release; the page and `forecast.json` MUST therefore not be cached for longer than that.
- **FR-018**: Every response MUST carry these protections: forced secure transport, no content-type guessing, a restricted referrer policy, no framing of the site by other sites, and a content security policy that allows only the page's own code and the two outside services the page uses (the weather station's chart images and the current-conditions data), and nothing else.
- **FR-019**: The content security policy MUST be derived from the page that is actually deployed, so adding or changing the page's own code cannot silently break the page or silently widen the policy.
- **FR-020**: The settings cookie set by the page (001 FR-016) MUST keep working on the deployed site, including being marked secure.

**Cost, access and privacy**

- **FR-021**: The deployment MUST work within Firebase's free plan, MUST NOT require a billing account, and MUST NOT use any paid feature.
- **FR-022**: The deployment MUST use credentials created only for this purpose, allowed to publish the site and nothing else in the project.
- **FR-023**: Credentials MUST be kept outside the repository and the container image, readable only by the owner on the owner's computer, supplied to the container only when a run starts, and never written to logs or output. The system MUST refuse to deploy if the credentials file is readable by other users.
- **FR-024**: The deployed site MUST NOT include analytics, advertising or any other tracking, and MUST NOT collect or store personal data (001 FR-015).
- **FR-025**: The system MUST work without the weather station chart or the current-conditions service being reachable; neither is a deployment dependency.

**Replacing the interim publisher**

- **FR-026**: Once this feature is live, the interim publisher that pushes the site to a git remote MUST be removed from the run, and no hosting credentials or remotes for it MUST remain in the project.
- **FR-027**: A written one-time setup guide MUST cover everything the owner has to do in the Firebase console and on their computer to enable deployment, so it can be repeated from nothing.

### Key Entities

- **Hosting Site**: The public site in the Firebase project (project identifier, site identifier, public addresses).
- **Release**: One version of the site that has been deployed (identifier, time, forecast cycle, files, bytes, whether live, whether a preview).
- **Deployment Record**: What was recorded for one attempt (run, cycle, outcome, reason if failed, release identifier, checks made, address verified, duration).
- **Deployment Credentials**: The access the system uses to publish (purpose, permissions, where stored, last rotated).
- **Pre-deployment Checks**: The list of conditions a page must meet before it may be deployed.
- **Header Policy**: The set of protections and caching rules sent with every response.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A pilot can open the forecast at its public address at any hour, with the owner's computer off, and sees a forecast that is no older than the last successful run.
- **SC-002**: A new forecast is visible to a returning visitor within 5 minutes of the run that produced it finishing.
- **SC-003**: In 100% of tested failure cases (failed run, failed checks, interrupted upload, hosting outage, revoked credentials) the previous release stays live and the failure is recorded.
- **SC-004**: The deployment step adds no more than 2 minutes to a run.
- **SC-005**: The owner can restore the previous release in under 5 minutes, and a preview in under 5 minutes.
- **SC-006**: The deployed page's first load takes under 1 second on a typical mobile connection in Victoria, and its total size stays under 200 KB (excluding the weather station's chart images, which come from another provider).
- **SC-007**: At expected traffic (about 1,000 visits a day) usage stays under 50% of the free plan's monthly limits, and no charge is ever incurred.
- **SC-008**: A search of the repository, the container image and the run logs finds no credentials.
- **SC-009**: Every required security header is present on 100% of checked responses, and the page makes no request to any host outside the two allowed services.
- **SC-010**: Following the setup guide from nothing, the owner can reach a working deployment in under 60 minutes.

## Assumptions

- The Firebase project `free-flying-forecast` already exists (the owner supplied its console link) and the owner has full control of it. As checked on 2026-10-03, both default addresses answer with Firebase's "Site Not Found" page, which means nothing has been deployed yet.
- The project stays on Firebase's free (Spark) plan. Third-party sources report this plan as 10 GB of stored data and 10 GB of data transfer a month, with no billing account and no charges (when a limit is reached the site stops responding until it resets). These figures are NOT from Firebase's own pricing page and MUST be confirmed there before launch.
- At about 100 KB per visit from Firebase (the weather station's chart comes from another provider), the free transfer limit corresponds to roughly 100,000 visits a month, far above the expected club-level traffic.
- Unattended publishing uses a dedicated service account with only the Hosting publisher role and its key file, as Firebase's own guidance recommends for non-interactive use; token-based sign-in is deprecated and is not used. The choice of publishing tool (the official command-line tool or the Hosting programming interface) is left to the plan, constrained by FR-006 and by running in the Linux container on the iMac.
- The default `web.app` address is the public address for the first version. A custom domain is out of scope but must remain possible later.
- The page and its data are static files; no server-side code, database or user accounts are needed (001 constraints).
- Setting up the Firebase project (enabling Hosting, creating the service account) is a one-time manual step by the owner, described in the setup guide; it is not automated.
- Notifications beyond the owner-only status (for example email or a phone alert) are a later improvement; the spec requires only that failures are clearly flagged there (FR-013).
- The weather station chart and the current-conditions panel keep working unchanged on the deployed site, as optional extras (001 FR-012c and FR-018).

## Out of Scope

- A custom domain, a content delivery tuning exercise, multiple sites or regions.
- Server-side features, forms, accounts, analytics, advertising or A/B testing.
- Restricting who can view the site.
- Automating the one-time Firebase project setup.
- Email or phone notifications.
