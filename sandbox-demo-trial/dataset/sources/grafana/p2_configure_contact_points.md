# Configure contact points

Use contact points to specify where to receive alert notifications. Contact points contain the configuration for sending alert notifications, including destinations like email, Slack, IRM, webhooks, and their notification messages.

A contact point can have one or multiple destinations, known as contact point integrations. Alert notifications are sent to each integration within the chosen contact point.

On the **Contact Points** tab, you can:

- Add, edit, and view contact points and integrations.
- Search for name and type of contact points and integrations.
- View how many notification policies each contact point is being used for and navigate directly to the linked notification policies.
- View the status of notification deliveries.
- Export individual contact points or all contact points in JSON, YAML, or Terraform format.
- Delete contact points. Note that you cannot delete contact points that are in use by a notification policy. To proceed, either delete the notification policy or update it to use another contact point.

> Note: Contact points are assigned to a specific Alertmanager and cannot be used by notification policies in other Alertmanagers.

## Grafana Cloud Protected fields

For Grafana Cloud users, contact points may contain protected fields that require admin permissions to modify. Protected fields are sensitive configuration settings that affect where notifications are sent, such as:

- Target URLs for integrations (webhooks, PagerDuty, Opsgenie, or other integrations.)
- API endpoints
- Other destination-related settings

These fields are protected to prevent unauthorized users from redirecting notifications to compromised servers, which could expose sensitive information such as authorization tokens, API keys, or alert data.

Users with edit permissions can modify most contact point settings and can add or remove integrations, but cannot change protected fields in existing integrations. Only users with admin permissions to the contact point can update protected fields.

The ability to modify protected fields is controlled by the RBAC action `alert.notifications.receivers.protected:write`. This role is granted by default to:

- Users with the fixed "Alerting Admin" role
- Users with admin permissions for the specific contact point

## Supported contact point integrations

Each contact point integration has its own configuration options and setup process. The following list shows the contact point integrations supported by Grafana:

- Alertmanager
- AWS SNS
- Cisco Webex Teams
- DingDing
- Discord
- Email
- Google Chat
- Grafana IRM
- Kafka REST Proxy
- Jira
- Line
- Microsoft Teams
- MQTT
- Opsgenie
- PagerDuty
- Pushover
- Sensu Go
- Slack
- Telegram
- Threema Gateway
- VictorOps
- Webhook
- WeCom

Some of the integrations above are not supported by Prometheus Alertmanager. For the list of supported integrations, refer to the Prometheus Alertmanager receiver settings.

## Add a contact point

Complete the following steps to add a contact point:

1. In the left-side menu, click **Alerts & IRM** and then **Alerting**.
2. Click **Notification configuration**, then select the **Contact points** tab.
3. From the **Choose Alertmanager** dropdown, select an Alertmanager. By default, **Grafana Alertmanager** is selected.
4. Click **+ New contact point**.
5. Enter a descriptive name for the contact point.
6. From **Integration**, select a type and fill out mandatory fields. For example, if you choose email, enter the email addresses. Or if you choose Slack, enter the Slack channel and users who should be contacted.
7. Some contact point integrations, like email or Webhook, have optional settings. In **Optional settings**, specify additional settings for the selected contact point integration.
8. In Notification settings, optionally select **Disable resolved message** if you do not want to be notified when an alert resolves.
9. Save your changes.

## Add another contact point integration

A contact point can have multiple integrations, or destinations for sending notifications.

To add another integration to a contact point, complete the following steps:

1. Add or edit an existing contact point.
2. Click **Add contact point integration** and repeat the same steps as adding a contact point.
   - From **Integration**, select a type and fill out mandatory fields.
   - In **Optional settings**, specify additional settings for the selected contact point integration.
3. Save your changes.

## Customize notification messages

In contact points, you can also customize notification messages. For example, when setting up an email contact point integration, click **Message** or **Subject** to modify it.

By default, notification messages include common alert details, which are usually sufficient for most cases.

If necessary, you can customize the content and format of notification messages. You can create a custom notification template, which can then be applied to one or more contact points.

On the **Templates** tab under **Notification configuration**, you can view, edit, copy or delete notification templates.

## Test a contact point

Testing a contact point is only available for Grafana Alertmanager. Complete the following steps to test a contact point:

1. In the left-side menu, click **Alerts & IRM** and then **Alerting**.
2. Click **Notification configuration**, then select the **Contact points** tab to view a list of existing contact points.
3. Find the contact point you want to test, then click **Edit**. You can also create a new contact point if needed.
4. Click **Test** to open the contact point testing dialog box.
5. Choose whether to send a predefined test notification or choose custom to add your own custom annotations and labels to include in the notification.
6. Click **Send test notification** to fire the alert.

## Enable notifications for a contact point

After creating a contact point, you can enable it to receive alert notifications using one of the following methods:

- **Assign it to alert rules** -- Select the contact point in the notifications options for Grafana-managed alert rules to directly associate it with specific alerts.
- **Assign it to notification policies** -- Add the contact point to one or more notification policies, which manage the alert notifications you want the contact point to receive.
