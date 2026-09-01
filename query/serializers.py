from rest_framework import serializers


class QueryRequestSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=2000)
    top_k = serializers.IntegerField(default=5, min_value=1, max_value=20)
    include_restricted = serializers.BooleanField(default=False)


class StatsRequestSerializer(serializers.Serializer):
    group_by = serializers.ChoiceField(
        choices=["source_type", "source_name", "access_level"],
        default="source_type",
    )
