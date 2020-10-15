from django.db import models
from .workflow import Workflow
from cjwkernel.types import Tab as ArrowTab
from cjwstate import clientside


class Tab(models.Model):
    """A sequence of Steps in a Workflow."""

    class Meta:
        app_label = "server"
        db_table = "tab"
        ordering = ["position"]
        unique_together = (("workflow", "slug"),)

    workflow = models.ForeignKey(
        Workflow, related_name="tabs", on_delete=models.CASCADE
    )
    slug = models.SlugField(db_index=False)
    """
    Unique ID, generated by the client.

    Within a Workflow, each tab has a different slug. The client randomly
    generates it so that the client can queue up requests that relate to it,
    before the Tab is even created in the database (i.e., before it gets an
    ID). When duplicating a Workflow, we duplicate all its Tabs' slugs.

    Slugs are unique per Workflow, and non-reusable. Even after deleting a Tab,
    the slug cannot be reused. (This requirement lets us use a database UNIQUE
    INDEX and support soft-deleting.)
    """

    name = models.TextField()
    position = models.IntegerField()
    selected_step_position = models.IntegerField(null=True)
    is_deleted = models.BooleanField(default=False)

    @property
    def live_steps(self):
        return self.steps.filter(is_deleted=False)

    def duplicate_into_new_workflow(self, to_workflow: Workflow) -> None:
        """Deep-copy this Tab to a new Tab in `to_workflow`."""
        assert to_workflow.id != self.workflow_id

        new_tab = to_workflow.tabs.create(
            slug=self.slug,
            name=self.name,
            position=self.position,
            selected_step_position=self.selected_step_position,
        )
        steps = list(self.live_steps)
        for step in steps:
            step.duplicate_into_new_workflow(new_tab)

    def to_arrow(self) -> ArrowTab:
        return ArrowTab(self.slug, self.name)

    def to_clientside(self) -> clientside.TabUpdate:
        return clientside.TabUpdate(
            slug=self.slug,
            name=self.name,
            selected_step_index=self.selected_step_position,
            step_ids=list(self.live_steps.values_list("id", flat=True)),
        )