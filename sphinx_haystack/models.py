from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic


class Document(models.Model):
    """
    This class replaces the haystack SearchResult class.

    This model exists to ensure that each document has a unique ID to use
    with Sphinx as it's document ID.

    Without this model, we would not be able to index different types of
    models using Sphinx. Two different models could inhabit the same key
    space which would result in duplicate document IDs.
    """
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField()
    object = generic.GenericForeignKey('content_type', 'object_id')

    def __init__(self, *args, **kwargs):
        self._score = kwargs.pop('score', None)
        super(Document, self).__init__(*args, **kwargs)

    def _get_score(self):
        """
        Retrieves the score from a private attribute (or 0 if missing).
        """
        return getattr(self, '_score', 0)

    def _set_score(self, value):
        """
        Sets the score to a private attribute.
        """
        setattr(self, '_score', value)

    score = property(_get_score, _set_score)
    """
    Handles the score when being used as search result.
    """

    @property
    def model(self):
        return self.content_type.model_class()