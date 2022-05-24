from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class Absence(models.Model):
    ID = models.AutoField(primary_key=True)
    User_ID = models.ForeignKey(User, on_delete=models.CASCADE, related_name="absences")
    absence_date_start = models.DateField(max_length=200)
    absence_date_end = models.DateField(max_length=200)

    def __str__(self):
        return f"{self.User_ID}, {self.absence_date_start} - {self.absence_date_end}"


class Team(models.Model):
    """ This includes all the attributes of a Team """
    id          = models.AutoField(primary_key=True)
    name        = models.CharField(max_length=128, unique=True, null=False)
    description = models.CharField(max_length=512)
    private     = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.name}"

    @property
    def count(self):
        return Relationship.objects.filter(team=self).count()

class Role(models.Model):
    """ This includes all the attributes of a Role """
    id              = models.AutoField(primary_key=True)
    role            = models.CharField(max_length=64, null=False, unique=True)

    def __str__(self):
        return f"{self.role}"

class Relationship(models.Model):
    """ This includes all the attributes of a Relationship """
    id          = models.AutoField(primary_key=True)
    user        = models.ForeignKey(User, on_delete=models.CASCADE)
    team        = models.ForeignKey(Team, on_delete=models.CASCADE)
    role        = models.ForeignKey(Role, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'team',)

    def __str__(self):
        return f"{self.user.username} | {self.team.name} | {self.role}"
