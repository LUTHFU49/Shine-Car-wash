from django import forms

from .models import Feedback, FeedbackStatus

FORM_INPUT_CLASSES = (
    'w-full rounded-lg border border-slate-700 bg-slate-900/60 px-3.5 py-2.5 text-sm text-white placeholder-gray-500 '
    'focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-colors'
)

RATING_CHOICES = [(i, f'{i} star{"s" if i != 1 else ""}') for i in range(5, 0, -1)]


class ReviewForm(forms.Form):
    rating = forms.ChoiceField(choices=RATING_CHOICES, widget=forms.RadioSelect)
    comment = forms.CharField(
        required=False, max_length=1000,
        widget=forms.Textarea(attrs={'class': FORM_INPUT_CLASSES, 'rows': 4, 'maxlength': 1000, 'placeholder': 'Tell us more (optional)'}),
    )


class ReviewResponseForm(forms.Form):
    response = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(attrs={'class': FORM_INPUT_CLASSES, 'rows': 4, 'maxlength': 1000}),
    )


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ['feedback_type', 'subject', 'message']
        widgets = {
            'feedback_type': forms.Select(attrs={'class': FORM_INPUT_CLASSES}),
            'subject': forms.TextInput(attrs={'class': FORM_INPUT_CLASSES}),
            'message': forms.Textarea(attrs={'class': FORM_INPUT_CLASSES, 'rows': 5, 'maxlength': 2000}),
        }


class FeedbackResponseForm(forms.Form):
    response = forms.CharField(
        max_length=2000,
        widget=forms.Textarea(attrs={'class': FORM_INPUT_CLASSES, 'rows': 4, 'maxlength': 2000}),
    )
    status = forms.ChoiceField(
        choices=FeedbackStatus.choices, widget=forms.Select(attrs={'class': FORM_INPUT_CLASSES}),
    )
