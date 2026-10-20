
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseRedirect
from django.contrib.auth.models import User
from django.contrib.auth import login, logout, authenticate
from django.urls import reverse
from django.views import generic
import logging

from .models import Course, Enrollment, Question, Choice, Submission

logger = logging.getLogger(__name__)


def registration_request(request):
    context = {}

    if request.method == 'GET':
        return render(
            request,
            'onlinecourse/user_registration_bootstrap.html',
            context
        )

    elif request.method == 'POST':
        username = request.POST['username']
        password = request.POST['psw']
        first_name = request.POST['firstname']
        last_name = request.POST['lastname']

        user_exist = False

        try:
            User.objects.get(username=username)
            user_exist = True
        except User.DoesNotExist:
            logger.info("New user registration")

        if not user_exist:
            user = User.objects.create_user(
                username=username,
                first_name=first_name,
                last_name=last_name,
                password=password
            )
            login(request, user)
            return redirect('onlinecourse:index')

        context['message'] = "User already exists."
        return render(
            request,
            'onlinecourse/user_registration_bootstrap.html',
            context
        )


def login_request(request):
    context = {}

    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['psw']

        user = authenticate(username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')

        context['message'] = "Invalid username or password."
        return render(
            request,
            'onlinecourse/user_login_bootstrap.html',
            context
        )

    return render(
        request,
        'onlinecourse/user_login_bootstrap.html',
        context
    )


def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


def check_if_enrolled(user, course):
    if user.is_authenticated:
        return Enrollment.objects.filter(
            user=user,
            course=course
        ).exists()

    return False


class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        user = self.request.user
        courses = Course.objects.order_by('-total_enrollment')[:10]

        for course in courses:
            if user.is_authenticated:
                course.is_enrolled = check_if_enrolled(user, course)

        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_detail_bootstrap.html'


def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    if user.is_authenticated:
        is_enrolled = check_if_enrolled(user, course)

        if not is_enrolled:
            Enrollment.objects.create(
                user=user,
                course=course,
                mode='honor'
            )
            course.total_enrollment += 1
            course.save()

    return HttpResponseRedirect(
        reverse(
            'onlinecourse:course_details',
            args=(course.id,)
        )
    )


def extract_answers(request):
    submitted_answers = []

    for key in request.POST:
        if key.startswith('choice'):
            value = request.POST[key]

            try:
                choice_id = int(value)
                submitted_answers.append(choice_id)
            except (ValueError, TypeError):
                continue

    return submitted_answers


def submit(request, course_id):
    if request.method != 'POST':
        return redirect(
            'onlinecourse:course_details',
            course_id=course_id
        )

    if not request.user.is_authenticated:
        return redirect('onlinecourse:login')

    course = get_object_or_404(Course, pk=course_id)

    enrollment = get_object_or_404(
        Enrollment,
        user=request.user,
        course=course
    )

    submission = Submission.objects.create(
        enrollment=enrollment
    )

    answer_ids = extract_answers(request)

    for choice_id in answer_ids:
        choice = get_object_or_404(
            Choice,
            pk=choice_id,
            question__course=course
        )
        submission.choices.add(choice)

    return redirect(
        'onlinecourse:show_exam_result',
        course_id=course.id,
        submission_id=submission.id
    )


def show_exam_result(request, course_id, submission_id):
    if not request.user.is_authenticated:
        return redirect('onlinecourse:login')

    course = get_object_or_404(Course, pk=course_id)

    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__course=course,
        enrollment__user=request.user
    )

    selected_ids = set(
        submission.choices.values_list('id', flat=True)
    )

    questions = Question.objects.filter(
        course=course
    ).prefetch_related('choices')

    question_results = []
    total_score = 0
    max_score = 0

    for question in questions:
        choices = list(question.choices.all())

        correct_ids = {
            choice.id
            for choice in choices
            if choice.is_correct
        }

        selected_for_question = [
            choice
            for choice in choices
            if choice.id in selected_ids
        ]

        selected_for_question_ids = {
            choice.id for choice in selected_for_question
        }

        is_correct = (
            bool(correct_ids)
            and selected_for_question_ids == correct_ids
        )

        max_score += question.grade
        earned_score = question.grade if is_correct else 0
        total_score += earned_score

        question_results.append({
            'question': question,
            'choices': choices,
            'selected_choices': selected_for_question,
            'correct_choices': [
                choice
                for choice in choices
                if choice.is_correct
            ],
            'is_correct': is_correct,
            'grade': earned_score,
        })

    submission.total_score = total_score
    submission.save(update_fields=['total_score'])

    passed = (
        max_score > 0
        and total_score >= max_score * 0.8
    )

    context = {
        'course': course,
        'submission': submission,
        'question_results': question_results,
        'total_score': total_score,
        'max_score': max_score,
        'passed': passed,
    }

    return render(
        request,
        'onlinecourse/exam_result_bootstrap.html',
        context
    )
